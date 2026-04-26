"""
routes/offers.py — Offers Management
Create discount offers that can be applied during inquiry/admission.
"""
from flask import Blueprint, current_app, render_template, request, redirect, url_for, flash, jsonify, session
from database import get_db, close_db
from routes.auth import login_required, role_required
from routes.offer_helpers import (
    apply_offer_discount,
    apply_offer_search,
    build_offer_scope,
    fetch_applicable_offer,
    fetch_course_fees,
    fetch_offer,
    load_offer_locations,
    parse_offer_calculation_payload,
    parse_offer_search,
    render_offer_form,
    validate_offer_form,
)

offers_bp = Blueprint("offers", __name__, url_prefix="/offers")
@offers_bp.route("/")
@login_required
@role_required("admin","developer")
def index():
    search = parse_offer_search(request.args)
    conn = get_db(); cur = conn.cursor()
    query, params = build_offer_scope()
    query, params = apply_offer_search(query, params, search)
    cur.execute(query + " ORDER BY o.is_active DESC, o.created_at DESC;", params)
    offers = cur.fetchall(); close_db(conn, commit=False)
    return render_template("offers/index.html", offers=offers, search=search)

@offers_bp.route("/add", methods=["GET","POST"])
@login_required
@role_required("admin","developer")
def add():
    conn = get_db(); cur = conn.cursor()
    locations = load_offer_locations(cur)
    close_db(conn, commit=False)

    if request.method == "POST":
        try:
            cleaned = validate_offer_form(request.form)
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
            return render_offer_form(
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
            return render_offer_form(
                offer=None,
                locations=locations,
                action="Add",
                form_data=request.form.to_dict(flat=True),
                form_error_popup=message,
            )

    return render_offer_form(offer=None, locations=locations, action="Add")

@offers_bp.route("/<int:oid>/edit", methods=["GET","POST"])
@login_required
@role_required("admin","developer")
def edit(oid):
    conn = get_db(); cur = conn.cursor()
    offer = fetch_offer(cur, oid)
    locations = load_offer_locations(cur)
    close_db(conn, commit=False)
    if not offer: flash("Not found.","danger"); return redirect(url_for("offers.index"))

    if request.method == "POST":
        try:
            cleaned = validate_offer_form(request.form)
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
            return render_offer_form(
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
            return render_offer_form(
                offer=offer,
                locations=locations,
                action="Edit",
                form_data=request.form.to_dict(flat=True),
                form_error_popup=message,
            )

    return render_offer_form(offer=offer, locations=locations, action="Edit")

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
        course_id, offer_id = parse_offer_calculation_payload(data)
    except ValueError as exc:
        return jsonify({"ok": False, "msg": str(exc), "fees": 0}), 400
    if not course_id:
        return jsonify({"ok": False, "msg": "course_id is required", "fees": 0}), 400
    conn = get_db(); cur = conn.cursor()
    role = session.get("role")
    assigned_loc_id = session.get("location_id")
    fees = fetch_course_fees(cur, course_id, role, assigned_loc_id)
    if fees is None:
        close_db(conn,commit=False)
        return jsonify({"fees": 0})
    if offer_id:
        fees = apply_offer_discount(fees, fetch_applicable_offer(cur, offer_id, role, assigned_loc_id))
    close_db(conn, commit=False)
    return jsonify({"fees": fees})
