"""
routes/inquiries.py â€” Inquiries (HeavyLift CRM)
Features: auto-followup notification, optional refs, offer linkage, WhatsApp, Excel export
"""
from datetime import date, timedelta
import io
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import Blueprint, current_app, flash, jsonify, make_response, redirect, render_template, request, session, url_for

from config import Config
from database import close_db, get_db
from routes.inquiry_helpers import (
    build_whatsapp_api_endpoint,
    build_whatsapp_recipient,
    apply_inquiry_filters,
    build_whatsapp_url,
    build_inquiry_scope,
    calculate_total_fees,
    fetch_inquiry,
    load_form_options,
    load_index_lookups,
    parse_amount,
    parse_date,
    parse_index_filters,
    parse_sort_args,
    render_inquiry_form,
    validate_inquiry_form,
    validate_teacher_form_access,
)
from routes.auth import login_required, role_required
from routes.notifications import create_notification
from validation import clean_choice, clean_optional_text, parse_optional_int

inquiries_bp = Blueprint("inquiries", __name__, url_prefix="/inquiries")


def _send_whatsapp_via_api(mobile, message):
    endpoint = build_whatsapp_api_endpoint(Config.WA_API_URL, Config.WA_PHONE_ID)
    token = (Config.WA_API_TOKEN or "").strip()
    if not endpoint or not token:
        return None

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": build_whatsapp_recipient(mobile),
        "type": "text",
        "text": {
            "preview_url": False,
            "body": message or "",
        },
    }
    request_body = json.dumps(payload).encode("utf-8")
    req = Request(
        endpoint,
        data=request_body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(req, timeout=10) as response:
            response_body = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        current_app.logger.warning("WhatsApp API send failed: %s", error_body or exc.reason)
        return {"ok": False, "msg": "WhatsApp API rejected the message.", "details": error_body}
    except URLError as exc:
        current_app.logger.warning("WhatsApp API connection failed: %s", exc)
        return {"ok": False, "msg": "WhatsApp API is unreachable right now."}

    try:
        parsed = json.loads(response_body) if response_body else {}
    except json.JSONDecodeError:
        parsed = {}

    message_id = None
    if isinstance(parsed.get("messages"), list) and parsed["messages"]:
        message_id = parsed["messages"][0].get("id")
    return {"ok": True, "msg": "WhatsApp message sent.", "message_id": message_id}


@inquiries_bp.route("/")
@login_required
def index():
    role = session.get("role")
    loc_id = session.get("location_id")
    filters = parse_index_filters(request.args)
    sort_col, sort_dir = parse_sort_args(request.args)

    base, params = build_inquiry_scope(role, loc_id)
    base, params, warnings = apply_inquiry_filters(base, params, filters)
    for warning in warnings:
        flash(warning, "warning")

    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"SELECT i.*,l.name AS location_name,c.name AS course_name,o.name AS offer_name {base} ORDER BY {sort_col} {sort_dir};", params)
    inquiries = cur.fetchall()
    locations, courses = load_index_lookups(cur, role, loc_id)
    close_db(conn, commit=False)
    return render_template(
        "inquiries/index.html",
        inquiries=inquiries,
        locations=locations,
        courses=courses,
        filters=filters,
        sort_col=sort_col,
        sort_dir=sort_dir,
        today=date.today(),
    )


@inquiries_bp.route("/add", methods=["GET", "POST"])
@login_required
@role_required("admin", "developer", "teacher")
def add():
    role = session.get("role")
    assigned_loc_id = session.get("location_id")
    conn = get_db()
    cur = conn.cursor()
    locs, courses_list, offers = load_form_options(cur, role, assigned_loc_id)
    close_db(conn, commit=False)

    defaults = {
        "inquiry_date": date.today().isoformat(),
        "followup_date": (date.today() + timedelta(days=10)).isoformat(),
    }

    if request.method == "POST":
        form = request.form
        try:
            location_id = parse_optional_int(form.get("location_id"), "Location")
            if role == "teacher" and assigned_loc_id:
                location_id = assigned_loc_id
            course_id = parse_optional_int(form.get("course_id"), "Course")
            offer_id = parse_optional_int(form.get("offer_id"), "Offer")
            fees_total = calculate_total_fees(course_id, offer_id)
            cleaned = validate_inquiry_form(form, fees_total)
            if role == "teacher" and assigned_loc_id:
                conn_check = get_db()
                cur_check = conn_check.cursor()
                try:
                    validate_teacher_form_access(cur_check, course_id, offer_id, assigned_loc_id)
                finally:
                    close_db(conn_check, commit=False)
            conn = get_db()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO inquiries
                  (name,gender,mobile,location_id,city,state,course_id,offer_id,
                   inquiry_date,followup_date,admission_date,status,fees_total,fees_paid,
                   ref1_name,ref1_mobile,ref2_name,ref2_mobile,ref3_name,ref3_mobile)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
                """,
                (
                    cleaned["name"],
                    cleaned["gender"],
                    cleaned["mobile"],
                    location_id,
                    cleaned["city"],
                    cleaned["state"],
                    course_id,
                    offer_id,
                    cleaned["inquiry_date"],
                    cleaned["followup_date"],
                    cleaned["admission_date"],
                    cleaned["status"],
                    fees_total,
                    cleaned["fees_paid"],
                    cleaned["ref1_name"],
                    cleaned["ref1_mobile"],
                    cleaned["ref2_name"],
                    cleaned["ref2_mobile"],
                    cleaned["ref3_name"],
                    cleaned["ref3_mobile"],
                ),
            )
            close_db(conn)
            create_notification(
                f"Follow-up due: {cleaned['name']}",
                f"Follow-up scheduled on {cleaned['followup_date'] or 'N/A'} for {cleaned['name']} ({cleaned['mobile']}).",
                target_role="admin",
            )
            flash("Inquiry added.", "success")
            return redirect(url_for("inquiries.index"))
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_inquiry_form(
                inquiry=None,
                locations=locs,
                courses=courses_list,
                offers=offers,
                defaults=defaults,
                action="Add",
                form_data=request.form.to_dict(flat=True),
                form_error_popup=str(exc),
            )
        except Exception:
            current_app.logger.exception("Failed to add inquiry")
            message = "Unable to save inquiry right now."
            flash(message, "danger")
            return render_inquiry_form(
                inquiry=None,
                locations=locs,
                courses=courses_list,
                offers=offers,
                defaults=defaults,
                action="Add",
                form_data=request.form.to_dict(flat=True),
                form_error_popup=message,
            )

    return render_inquiry_form(
        inquiry=None,
        locations=locs,
        courses=courses_list,
        offers=offers,
        defaults=defaults,
        action="Add",
    )


@inquiries_bp.route("/<int:iid>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin", "developer", "teacher")
def edit(iid):
    role = session.get("role")
    loc_id = session.get("location_id")
    conn = get_db()
    cur = conn.cursor()
    inquiry = fetch_inquiry(cur, iid, role, loc_id)
    locs, courses_list, offers = load_form_options(cur, role, loc_id)
    close_db(conn, commit=False)
    if not inquiry:
        flash("Not found.", "danger")
        return redirect(url_for("inquiries.index"))

    if request.method == "POST":
        form = request.form
        try:
            fees_total = parse_amount(form.get("fees_total", "0"), "Fees total")
            cleaned = validate_inquiry_form(form, fees_total)
            location_id = parse_optional_int(form.get("location_id"), "Location")
            course_id = parse_optional_int(form.get("course_id"), "Course")
            offer_id = parse_optional_int(form.get("offer_id"), "Offer")
            conn = get_db()
            cur = conn.cursor()
            if not fetch_inquiry(cur, iid, role, loc_id):
                close_db(conn, commit=False)
                flash("Not found.", "danger")
                return redirect(url_for("inquiries.index"))
            if role == "teacher" and loc_id:
                try:
                    validate_teacher_form_access(cur, course_id, offer_id, loc_id)
                except ValueError:
                    close_db(conn, commit=False)
                    raise
            cur.execute(
                """
                UPDATE inquiries SET
                  name=%s,gender=%s,mobile=%s,location_id=%s,city=%s,state=%s,
                  course_id=%s,offer_id=%s,inquiry_date=%s,followup_date=%s,
                  admission_date=%s,status=%s,fees_total=%s,fees_paid=%s,
                  ref1_name=%s,ref1_mobile=%s,ref2_name=%s,ref2_mobile=%s,
                  ref3_name=%s,ref3_mobile=%s
                WHERE id=%s;
                """,
                (
                    cleaned["name"],
                    cleaned["gender"],
                    cleaned["mobile"],
                    loc_id if role == "teacher" and loc_id else location_id,
                    cleaned["city"],
                    cleaned["state"],
                    course_id,
                    offer_id,
                    cleaned["inquiry_date"],
                    cleaned["followup_date"],
                    cleaned["admission_date"],
                    cleaned["status"],
                    fees_total,
                    cleaned["fees_paid"],
                    cleaned["ref1_name"],
                    cleaned["ref1_mobile"],
                    cleaned["ref2_name"],
                    cleaned["ref2_mobile"],
                    cleaned["ref3_name"],
                    cleaned["ref3_mobile"],
                    iid,
                ),
            )
            close_db(conn)
            flash("Updated.", "success")
            return redirect(url_for("inquiries.index"))
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_inquiry_form(
                inquiry=inquiry,
                locations=locs,
                courses=courses_list,
                offers=offers,
                defaults={},
                action="Edit",
                form_data=request.form.to_dict(flat=True),
                form_error_popup=str(exc),
            )
        except Exception:
            current_app.logger.exception("Failed to update inquiry %s", iid)
            message = "Unable to update inquiry right now."
            flash(message, "danger")
            return render_inquiry_form(
                inquiry=inquiry,
                locations=locs,
                courses=courses_list,
                offers=offers,
                defaults={},
                action="Edit",
                form_data=request.form.to_dict(flat=True),
                form_error_popup=message,
            )

    return render_inquiry_form(
        inquiry=inquiry,
        locations=locs,
        courses=courses_list,
        offers=offers,
        defaults={},
        action="Edit",
    )


@inquiries_bp.route("/<int:iid>/delete", methods=["POST"])
@login_required
@role_required("admin", "developer")
def delete(iid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM inquiries WHERE id=%s;", (iid,))
    close_db(conn)
    flash("Deleted.", "success")
    return redirect(url_for("inquiries.index"))


@inquiries_bp.route("/<int:iid>/convert", methods=["POST"])
@login_required
@role_required("admin", "developer", "teacher")
def convert(iid):
    role = session.get("role")
    loc_id = session.get("location_id")
    conn = get_db()
    cur = conn.cursor()
    inquiry = fetch_inquiry(cur, iid, role, loc_id)
    if not inquiry:
        close_db(conn, commit=False)
        flash("Not found.", "danger")
        return redirect(url_for("inquiries.index"))
    cur.execute(
        "UPDATE inquiries SET status='Converted', admission_date=COALESCE(admission_date,CURRENT_DATE) WHERE id=%s;",
        (iid,),
    )
    close_db(conn)
    create_notification(f"Admission: {inquiry['name']}", f"{inquiry['name']} has been converted to a student.", "admin")
    flash(f"{inquiry['name']} converted to student.", "success")
    return redirect(url_for("inquiries.index"))


@inquiries_bp.route("/<int:iid>/followup", methods=["GET", "POST"])
@login_required
@role_required("admin", "developer", "teacher")
def followup(iid):
    role = session.get("role")
    loc_id = session.get("location_id")
    conn = get_db()
    cur = conn.cursor()
    inquiry = fetch_inquiry(cur, iid, role, loc_id, with_joins=True)
    if not inquiry:
        close_db(conn, commit=False)
        flash("Not found.", "danger")
        return redirect(url_for("inquiries.index"))

    if request.method == "POST":
        try:
            conversation = clean_optional_text(request.form.get("conversation", ""), "Conversation", max_length=4000, multiline=True)
            followup_date = parse_date(request.form.get("followup_date"), "Follow-up date")
            status = clean_choice(request.form.get("status", inquiry["status"]), "Status", {"Open", "Converted", "Closed"})
            admission_date = parse_date(request.form.get("admission_date"), "Admission date")
            if followup_date and followup_date < inquiry["inquiry_date"]:
                raise ValueError("Follow-up date cannot be earlier than inquiry date.")
            if admission_date and admission_date < inquiry["inquiry_date"]:
                raise ValueError("Admission date cannot be earlier than inquiry date.")
            cur.execute(
                "INSERT INTO followups (inquiry_id,conversation,followup_date,status) VALUES (%s,%s,%s,%s);",
                (iid, conversation, followup_date.isoformat() if followup_date else None, status),
            )
            cur.execute(
                "UPDATE inquiries SET status=%s,followup_date=%s,admission_date=COALESCE(%s::date,admission_date) WHERE id=%s;",
                (status, followup_date.isoformat() if followup_date else None, admission_date.isoformat() if admission_date else None, iid),
            )
            close_db(conn)
            if followup_date:
                create_notification(f"Next follow-up: {inquiry['name']}", f"Scheduled for {followup_date.isoformat()}.", "admin")
            flash("Follow-up saved.", "success")
            return redirect(url_for("inquiries.followup", iid=iid))
        except ValueError as exc:
            flash(str(exc), "danger")
        except Exception:
            current_app.logger.exception("Failed to save follow-up for inquiry %s", iid)
            flash("Unable to save follow-up right now.", "danger")

    cur.execute("SELECT * FROM followups WHERE inquiry_id=%s ORDER BY created_at DESC;", (iid,))
    followups = cur.fetchall()
    close_db(conn, commit=False)
    default_next = (date.today() + timedelta(days=7)).isoformat()
    return render_template("inquiries/followup.html", inquiry=inquiry, followups=followups, default_next=default_next)


@inquiries_bp.route("/<int:iid>/whatsapp-send", methods=["POST"])
@login_required
def send_whatsapp(iid):
    """Send WhatsApp message via API when configured, otherwise return a wa.me link."""
    if not request.is_json:
        return jsonify({"ok": False, "msg": "JSON body required"}), 400
    role = session.get("role")
    loc_id = session.get("location_id")
    payload = request.get_json(silent=True) or {}
    conn = get_db()
    cur = conn.cursor()
    inquiry = fetch_inquiry(cur, iid, role, loc_id)
    if not inquiry:
        close_db(conn, commit=False)
        return jsonify({"ok": False, "msg": "Not found"}), 404

    try:
        msg_id = parse_optional_int(payload.get("msg_id"), "Message template")
        msg_text = clean_optional_text(payload.get("message"), "Message", max_length=2000, multiline=True) or ""
    except ValueError as exc:
        close_db(conn, commit=False)
        return jsonify({"ok": False, "msg": str(exc)}), 400
    if msg_id:
        cur.execute("SELECT description FROM whatsapp_msgs WHERE id=%s;", (msg_id,))
        template = cur.fetchone()
        if template:
            msg_text = (template["description"] or "").replace("[NAME]", inquiry["name"]).replace("[MOBILE]", inquiry["mobile"])
    close_db(conn, commit=False)

    try:
        api_result = _send_whatsapp_via_api(inquiry["mobile"], msg_text)
        if api_result is not None:
            status = 200 if api_result.get("ok") else 502
            return jsonify(api_result), status

        wa_url = build_whatsapp_url(inquiry["mobile"], msg_text)
    except ValueError as exc:
        return jsonify({"ok": False, "msg": str(exc)}), 400
    return jsonify({"ok": True, "url": wa_url, "msg": "WhatsApp chat opened."})


@inquiries_bp.route("/export")
@login_required
@role_required("admin", "developer", "teacher")
def export():
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill

    role = session.get("role")
    loc_id = session.get("location_id")
    base, params = build_inquiry_scope(role, loc_id)
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"SELECT i.*,l.name AS location_name,c.name AS course_name {base} ORDER BY i.inquiry_date DESC;", params)
    rows = cur.fetchall()
    close_db(conn, commit=False)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Inquiries"
    headers = [
        "ID", "Name", "Gender", "Mobile", "Location", "City", "State", "Course",
        "Inquiry Date", "Followup Date", "Admission Date", "Status",
        "Fees Total", "Fees Paid", "Pending", "Ref1 Name", "Ref1 Mobile",
    ]
    hfill = PatternFill("solid", fgColor="F59E0B")
    hfont = Font(color="000000", bold=True)
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.fill = hfill
        cell.font = hfont
        cell.alignment = Alignment(horizontal="center")
    for row_index, row in enumerate(rows, 2):
        pending = float(row.get("fees_total") or 0) - float(row.get("fees_paid") or 0)
        values = [
            row["id"], row["name"], row["gender"], row["mobile"], row["location_name"],
            row["city"], row["state"], row["course_name"],
            str(row["inquiry_date"]) if row["inquiry_date"] else "",
            str(row["followup_date"]) if row["followup_date"] else "",
            str(row["admission_date"]) if row["admission_date"] else "",
            row["status"], row.get("fees_total", 0), row.get("fees_paid", 0),
            pending, row.get("ref1_name", ""), row.get("ref1_mobile", ""),
        ]
        for col_index, value in enumerate(values, 1):
            ws.cell(row=row_index, column=col_index, value=value)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    response = make_response(buf.read())
    response.headers["Content-Disposition"] = "attachment; filename=inquiries.xlsx"
    response.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return response
