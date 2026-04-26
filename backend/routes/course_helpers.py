"""
course_helpers.py - shared helpers for course routes
"""
from flask import render_template

from validation import clean_optional_text, clean_text, parse_decimal, parse_optional_int


def validate_course_form(form):
    return {
        "name": clean_text(form.get("name"), "Course name", required=True, max_length=100),
        "description": clean_optional_text(form.get("description"), "Description", max_length=1000, multiline=True),
        "location_id": parse_optional_int(form.get("location_id"), "Location"),
        "fees": parse_decimal(form.get("fees", "0"), "Fees"),
    }


def render_course_form(*, course, locations, action, form_data=None, form_error_popup=None):
    return render_template(
        "courses/form.html",
        course=course,
        locations=locations,
        action=action,
        form_data=form_data or {},
        form_error_popup=form_error_popup,
    )


def parse_course_filters(args):
    return {
        "name": clean_text(args.get("name", ""), "Name", max_length=100),
        "location": clean_text(args.get("location", ""), "Location", max_length=100),
    }


def build_course_scope(role, assigned_loc_id):
    query = (
        "SELECT c.*, l.name AS location_name "
        "FROM courses c "
        "LEFT JOIN locations l ON c.location_id=l.id "
        "WHERE 1=1"
    )
    params = []
    if role == "teacher" and assigned_loc_id:
        query += " AND c.location_id=%s"
        params.append(assigned_loc_id)
    return query, params


def apply_course_filters(query, params, filters):
    if filters["name"]:
        query += " AND c.name ILIKE %s"
        params.append(f"%{filters['name']}%")
    if filters["location"]:
        query += " AND l.name ILIKE %s"
        params.append(f"%{filters['location']}%")
    return query, params


def load_course_locations(cur, role, assigned_loc_id):
    if role == "teacher" and assigned_loc_id:
        cur.execute("SELECT id,name FROM locations WHERE id=%s ORDER BY position,name;", (assigned_loc_id,))
    else:
        cur.execute("SELECT id,name FROM locations ORDER BY position,name;")
    return cur.fetchall()


def fetch_course(cur, course_id):
    cur.execute("SELECT * FROM courses WHERE id=%s;", (course_id,))
    return cur.fetchone()
