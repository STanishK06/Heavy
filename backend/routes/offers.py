"""
routes/offers.py — Offers Management
Create discount offers that can be applied during inquiry/admission.
"""
from flask import Blueprint, current_app, render_template, request, redirect, url_for, flash, jsonify, session
from database import get_db, close_db
from routes.auth import login_required, role_required
from validation import clean_choice, clean_optional_text, clean_text, parse_decimal, parse_optional_date, parse_optional_int

offers_bp = Blueprint("offers", __name__, url_prefix="/offers")


def _validate_offer_form(form):
    valid_from = parse_optional_date(form.get("valid_from"), "Valid from")
    valid_to = parse_optional_date(form.get("valid_to"), "Valid to")
    if valid_from and valid_to and valid_to < valid_from:
        raise ValueError("Valid to date cannot be earlier than valid from date.")
    return {
        "name": clean_text(form.get("name"), "Offer name", required=True, max_length=100),
        "description": clean_optional_text(form.get("description"), "Description", max_length=1000, multiline=True),
        "discount_type": clean_choice(form.get("discount_type", "flat"), "Discount type", {"flat", "percent"}),
        "discount_value": parse_decimal(form.get("discount_value", "0"), "Discount value"),
        "valid_from": valid_from,
        "valid_to": valid_to,
        "location_id": parse_optional_int(form.get("location_id"), "Location"),
        "is_active": str(form.get("is_active", "true")).lower() == "true",
    }


def _render_offer_form(*, offer, locations, action, form_data=None, form_error_popup=None):
    return render_template(
        "offers/form.html",
        offer=offer,
        locations=locations,
        action=action,
        form_data=form_data or {},
        form_error_popup=form_error_popup,
    )

@offers_bp.route("/")
@login_required
@role_required("admin","developer")
def index():
    search = clean_text(request.args.get("q",""), "Search", max_length=100)
    conn = get_db(); cur = conn.cursor()
    q = """SELECT o.*, l.name AS location_name FROM offers o
           LEFT JOIN locations l ON o.location_id=l.id WHERE 1=1"""
    p = []
    if search:
        q += " AND o.name ILIKE %s"; p.append(f"%{search}%")
    q += " ORDER BY o.is_active DESC, o.created_at DESC;"
    cur.execute(q, p)
    offers = cur.fetchall(); close_db(conn, commit=False)
    return render_template("offers/index.html", offers=offers, search=search)

@offers_bp.route("/add", methods=["GET","POST"])
@login_required
@role_required("admin","developer")
def add():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id,name FROM locations ORDER BY position,name;")
    locations = cur.fetchall(); close_db(conn, commit=False)

    if request.method == "POST":
        try:
            cleaned = _validate_offer_form(request.form)
            conn = get_db(); cur = conn.cursor()
            cur.execute("""
                INSERT INTO offers (name,description,discount_type,discount_value,
                                    valid_from,valid_to,location_id,is_active)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s);
            """, (
                cleaned["name"], cleaned["description"],
                cleaned["discount_type"], cleaned["discount_value"],
                cleaned["valid_from"], cleaned["valid_to"],
                cleaned["location_id"], cleaned["is_active"]
            ))
            close_db(conn); flash("Offer created.","success")
            return redirect(url_for("offers.index"))
        except ValueError as exc:
            flash(str(exc), "danger")
            return _render_offer_form(
                offer=None,
                locations=locations,
                action="Add",
                form_data=request.form.to_dict(flat=True),
                form_error_popup=str(exc),
            )
        except Exception:
            current_app.logger.exception("Failed to create offer")
            close_db(conn,commit=False)
            message = "Unable to create the offer right now."
            flash(message,"danger")
            return _render_offer_form(
                offer=None,
                locations=locations,
                action="Add",
                form_data=request.form.to_dict(flat=True),
                form_error_popup=message,
            )

    return _render_offer_form(offer=None, locations=locations, action="Add")

@offers_bp.route("/<int:oid>/edit", methods=["GET","POST"])
@login_required
@role_required("admin","developer")
def edit(oid):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM offers WHERE id=%s;", (oid,))
    offer = cur.fetchone()
    cur.execute("SELECT id,name FROM locations ORDER BY position,name;")
    locations = cur.fetchall(); close_db(conn, commit=False)
    if not offer: flash("Not found.","danger"); return redirect(url_for("offers.index"))

    if request.method == "POST":
        try:
            cleaned = _validate_offer_form(request.form)
            conn = get_db(); cur = conn.cursor()
            cur.execute("""
                UPDATE offers SET name=%s,description=%s,discount_type=%s,discount_value=%s,
                                  valid_from=%s,valid_to=%s,location_id=%s,is_active=%s
                WHERE id=%s;
            """, (
                cleaned["name"], cleaned["description"],
                cleaned["discount_type"], cleaned["discount_value"],
                cleaned["valid_from"], cleaned["valid_to"],
                cleaned["location_id"], cleaned["is_active"],
                oid
            ))
            close_db(conn); flash("Updated.","success"); return redirect(url_for("offers.index"))
        except ValueError as exc:
            flash(str(exc), "danger")
            return _render_offer_form(
                offer=offer,
                locations=locations,
                action="Edit",
                form_data=request.form.to_dict(flat=True),
                form_error_popup=str(exc),
            )
        except Exception:
            current_app.logger.exception("Failed to update offer %s", oid)
            close_db(conn,commit=False)
            message = "Unable to update the offer right now."
            flash(message,"danger")
            return _render_offer_form(
                offer=offer,
                locations=locations,
                action="Edit",
                form_data=request.form.to_dict(flat=True),
                form_error_popup=message,
            )

    return _render_offer_form(offer=offer, locations=locations, action="Edit")

@offers_bp.route("/<int:oid>/delete", methods=["POST"])
@login_required
@role_required("admin","developer")
def delete(oid):
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM offers WHERE id=%s;", (oid,))
    close_db(conn); flash("Deleted.","success"); return redirect(url_for("offers.index"))

@offers_bp.route("/api/calculate", methods=["POST"])
@login_required
def calculate():
    """AJAX: given course_id + offer_id, return discounted fee."""
    if not request.is_json:
        return jsonify({"ok": False, "msg": "JSON body required", "fees": 0}), 400
    data = request.get_json(silent=True) or {}
    try:
        course_id = parse_optional_int(data.get("course_id"), "course_id")
        offer_id = parse_optional_int(data.get("offer_id"), "offer_id")
    except ValueError as exc:
        return jsonify({"ok": False, "msg": str(exc), "fees": 0}), 400
    if not course_id:
        return jsonify({"ok": False, "msg": "course_id is required", "fees": 0}), 400
    conn = get_db(); cur = conn.cursor()
    role = session.get("role")
    assigned_loc_id = session.get("location_id")
    if role == "teacher" and assigned_loc_id:
        cur.execute("SELECT fees FROM courses WHERE id=%s AND location_id=%s;", (course_id, assigned_loc_id))
    else:
        cur.execute("SELECT fees FROM courses WHERE id=%s;", (course_id,))
    c = cur.fetchone()
    if not c: close_db(conn,commit=False); return jsonify({"fees": 0})
    fees = float(c["fees"])
    if offer_id:
        if role == "teacher" and assigned_loc_id:
            cur.execute(
                """
                SELECT * FROM offers
                WHERE id=%s AND is_active=TRUE
                  AND (location_id IS NULL OR location_id=%s);
                """,
                (offer_id, assigned_loc_id),
            )
        else:
            cur.execute("SELECT * FROM offers WHERE id=%s AND is_active=TRUE;", (offer_id,))
        o = cur.fetchone()
        if o:
            if o["discount_type"] == "percent":
                fees -= fees * float(o["discount_value"]) / 100
            else:
                fees -= float(o["discount_value"])
            fees = max(0, fees)
    close_db(conn, commit=False)
    return jsonify({"fees": fees})
