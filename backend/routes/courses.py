"""
routes/courses.py — Courses with drag-order & analytics
"""
from flask import Blueprint, current_app, render_template, request, redirect, url_for, flash, jsonify, session
from database import get_db, close_db
from routes.auth import login_required, role_required
from routes.course_helpers import (
    apply_course_filters,
    build_course_scope,
    fetch_course,
    load_course_locations,
    parse_course_filters,
    render_course_form,
    validate_course_form,
)
from validation import validate_ordered_ids

courses_bp = Blueprint("courses", __name__, url_prefix="/courses")
@courses_bp.route("/")
@login_required
def index():
    filters = parse_course_filters(request.args)
    role = session.get("role")
    loc_id = session.get("location_id")
    conn = get_db(); cur = conn.cursor()

    query, params = build_course_scope(role, loc_id)
    query, params = apply_course_filters(query, params, filters)
    cur.execute(query + " ORDER BY c.position, c.created_at;", params)
    courses = cur.fetchall()
    locations = load_course_locations(cur, role, loc_id)
    close_db(conn, commit=False)
    return render_template(
        "courses/index.html",
        courses=courses,
        locations=locations,
        name_q=filters["name"],
        loc_q=filters["location"],
    )

@courses_bp.route("/add", methods=["GET","POST"])
@login_required
@role_required("admin","developer")
def add():
    role = session.get("role")
    loc_id = session.get("location_id")
    conn = get_db(); cur = conn.cursor()
    locations = load_course_locations(cur, role, loc_id)
    close_db(conn, commit=False)

    if request.method == "POST":
        try:
            cleaned = validate_course_form(request.form)
            conn = get_db(); cur = conn.cursor()
            cur.execute("SELECT COALESCE(MAX(position),0)+1 AS next_position FROM courses;")
            pos = cur.fetchone()["next_position"]
            cur.execute("INSERT INTO courses (name,description,location_id,fees,position) VALUES (%s,%s,%s,%s,%s);",
                        (cleaned["name"], cleaned["description"], cleaned["location_id"], cleaned["fees"], pos))
            close_db(conn); flash(f"Course '{cleaned['name']}' created.","success")
            return redirect(url_for("courses.index"))
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_course_form(
                course=None,
                locations=locations,
                action="Add",
                form_data=request.form.to_dict(flat=True),
                form_error_popup=str(exc),
            )
        except Exception:
            current_app.logger.exception("Failed to create course")
            close_db(conn,commit=False)
            message = "Unable to create the course right now."
            flash(message,"danger")
            return render_course_form(
                course=None,
                locations=locations,
                action="Add",
                form_data=request.form.to_dict(flat=True),
                form_error_popup=message,
            )

    return render_course_form(course=None, locations=locations, action="Add")

@courses_bp.route("/<int:cid>/edit", methods=["GET","POST"])
@login_required
@role_required("admin","developer")
def edit(cid):
    role = session.get("role")
    loc_id = session.get("location_id")
    conn = get_db(); cur = conn.cursor()
    course = fetch_course(cur, cid)
    locations = load_course_locations(cur, role, loc_id)
    close_db(conn, commit=False)
    if not course: flash("Not found.","danger"); return redirect(url_for("courses.index"))

    if request.method == "POST":
        try:
            cleaned = validate_course_form(request.form)
            conn = get_db(); cur = conn.cursor()
            cur.execute("UPDATE courses SET name=%s,description=%s,location_id=%s,fees=%s WHERE id=%s;",
                        (cleaned["name"], cleaned["description"], cleaned["location_id"], cleaned["fees"], cid))
            close_db(conn); flash("Updated.","success"); return redirect(url_for("courses.index"))
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_course_form(
                course=course,
                locations=locations,
                action="Edit",
                form_data=request.form.to_dict(flat=True),
                form_error_popup=str(exc),
            )
        except Exception:
            current_app.logger.exception("Failed to update course %s", cid)
            close_db(conn,commit=False)
            message = "Unable to update the course right now."
            flash(message,"danger")
            return render_course_form(
                course=course,
                locations=locations,
                action="Edit",
                form_data=request.form.to_dict(flat=True),
                form_error_popup=message,
            )
    return render_course_form(course=course, locations=locations, action="Edit")

@courses_bp.route("/<int:cid>/delete", methods=["POST"])
@login_required
@role_required("admin","developer")
def delete(cid):
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM courses WHERE id=%s;", (cid,))
    close_db(conn); flash("Deleted.","success"); return redirect(url_for("courses.index"))

@courses_bp.route("/reorder", methods=["POST"])
@login_required
@role_required("admin","developer")
def reorder():
    if not request.is_json:
        return jsonify({"ok": False, "msg": "JSON body required"}), 400
    payload = request.get_json(silent=True) or {}
    try:
        ids = validate_ordered_ids(payload.get("ids", []))
    except ValueError as exc:
        return jsonify({"ok": False, "msg": str(exc)}), 400
    conn = get_db(); cur = conn.cursor()
    for pos, cid in enumerate(ids):
        cur.execute("UPDATE courses SET position=%s WHERE id=%s;", (pos, cid))
    close_db(conn); return jsonify({"ok": True})

@courses_bp.route("/<int:cid>/analytics")
@login_required
def analytics(cid):
    conn = get_db(); cur = conn.cursor()
    role = session.get("role")
    assigned_loc_id = session.get("location_id")
    query = "SELECT c.*, l.name AS location_name FROM courses c LEFT JOIN locations l ON c.location_id=l.id WHERE c.id=%s"
    params = [cid]
    if role == "teacher" and assigned_loc_id:
        query += " AND c.location_id=%s"
        params.append(assigned_loc_id)
    cur.execute(query + ";", params)
    course = cur.fetchone()
    if not course: close_db(conn,commit=False); flash("Not found.","danger"); return redirect(url_for("courses.index"))

    cur.execute("""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN status='Converted' THEN 1 ELSE 0 END) AS enrolled,
               COALESCE(SUM(fees_paid),0) AS revenue,
               COALESCE(SUM(CASE WHEN status='Converted' THEN fees_total-fees_paid ELSE 0 END),0) AS pending
        FROM inquiries WHERE course_id=%s;
    """, (cid,))
    stats = cur.fetchone()

    cur.execute("""
        SELECT TO_CHAR(inquiry_date,'YYYY-MM') AS month, COUNT(*) AS inquiries,
               SUM(CASE WHEN status='Converted' THEN 1 ELSE 0 END) AS admissions
        FROM inquiries WHERE course_id=%s
        GROUP BY month ORDER BY month DESC LIMIT 12;
    """, (cid,))
    trend = list(reversed(cur.fetchall()))

    cur.execute("""
        SELECT i.*, l.name AS location_name
        FROM inquiries i LEFT JOIN locations l ON i.location_id=l.id
        WHERE i.course_id=%s ORDER BY i.inquiry_date DESC LIMIT 20;
    """, (cid,))
    inquiries = cur.fetchall()

    close_db(conn, commit=False)
    return render_template("courses/analytics.html",
                           course=course, stats=stats, trend=trend, inquiries=inquiries)
