"""
offer_helpers.py - shared helpers for offer routes
"""
from flask import render_template

from validation import clean_choice, clean_optional_text, clean_text, parse_decimal, parse_optional_date, parse_optional_int


def validate_offer_form(form):
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


def render_offer_form(*, offer, locations, action, form_data=None, form_error_popup=None):
    return render_template(
        "offers/form.html",
        offer=offer,
        locations=locations,
        action=action,
        form_data=form_data or {},
        form_error_popup=form_error_popup,
    )


def parse_offer_search(args):
    return clean_text(args.get("q", ""), "Search", max_length=100)


def build_offer_scope():
    return (
        "SELECT o.*, l.name AS location_name "
        "FROM offers o "
        "LEFT JOIN locations l ON o.location_id=l.id "
        "WHERE 1=1"
    ), []


def apply_offer_search(query, params, search):
    if search:
        query += " AND o.name ILIKE %s"
        params.append(f"%{search}%")
    return query, params


def load_offer_locations(cur):
    cur.execute("SELECT id,name FROM locations ORDER BY position,name;")
    return cur.fetchall()


def fetch_offer(cur, offer_id):
    cur.execute("SELECT * FROM offers WHERE id=%s;", (offer_id,))
    return cur.fetchone()


def parse_offer_calculation_payload(data):
    course_id = parse_optional_int(data.get("course_id"), "course_id")
    offer_id = parse_optional_int(data.get("offer_id"), "offer_id")
    return course_id, offer_id


def fetch_course_fees(cur, course_id, role, assigned_loc_id):
    if role == "teacher" and assigned_loc_id:
        cur.execute("SELECT fees FROM courses WHERE id=%s AND location_id=%s;", (course_id, assigned_loc_id))
    else:
        cur.execute("SELECT fees FROM courses WHERE id=%s;", (course_id,))
    course = cur.fetchone()
    return float(course["fees"]) if course else None


def fetch_applicable_offer(cur, offer_id, role, assigned_loc_id):
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
    return cur.fetchone()


def apply_offer_discount(fees, offer):
    if not offer:
        return fees
    if offer["discount_type"] == "percent":
        fees -= fees * float(offer["discount_value"]) / 100
    else:
        fees -= float(offer["discount_value"])
    return max(0, fees)
