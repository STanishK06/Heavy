"""
location_helpers.py - shared helpers for location routes
"""
from flask import render_template

from validation import clean_optional_text, clean_text


def validate_location_form(form):
    return {
        "name": clean_text(form.get("name"), "Location name", required=True, max_length=100),
        "description": clean_optional_text(form.get("description"), "Description", max_length=1000, multiline=True),
    }


def render_location_form(*, location, action, form_data=None, form_error_popup=None):
    return render_template(
        "locations/form.html",
        location=location,
        action=action,
        form_data=form_data or {},
        form_error_popup=form_error_popup,
    )


def parse_location_search(args):
    return clean_text(args.get("q", ""), "Search", max_length=100)


def build_location_scope(role, assigned_loc_id):
    query = "SELECT * FROM locations WHERE 1=1"
    params = []
    if role == "teacher" and assigned_loc_id:
        query += " AND id=%s"
        params.append(assigned_loc_id)
    return query, params


def apply_location_search(query, params, search):
    if search:
        query += " AND (name ILIKE %s OR description ILIKE %s)"
        params.extend([f"%{search}%", f"%{search}%"])
    return query, params


def fetch_location(cur, location_id):
    cur.execute("SELECT * FROM locations WHERE id=%s;", (location_id,))
    return cur.fetchone()
