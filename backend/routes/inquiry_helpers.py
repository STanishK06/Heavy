"""
inquiry_helpers.py - shared helpers for inquiry routes
"""
from datetime import date, timedelta

from flask import render_template

from database import close_db, get_db
from validation import clean_choice, clean_optional_text, clean_text, parse_optional_int

INQUIRY_STATUSES = {"Open", "Converted", "Closed"}
INQUIRY_SORT_COLUMNS = {
    "i.inquiry_date",
    "i.name",
    "i.mobile",
    "l.name",
    "c.name",
    "i.status",
    "i.followup_date",
}


def build_inquiry_scope(role, loc_id):
    base = (
        "FROM inquiries i "
        "LEFT JOIN locations l ON i.location_id=l.id "
        "LEFT JOIN courses c ON i.course_id=c.id "
        "LEFT JOIN offers o ON i.offer_id=o.id "
        "WHERE 1=1"
    )
    params = []
    if role == "teacher" and loc_id:
        base += " AND i.location_id=%s"
        params.append(loc_id)
    return base, params


def parse_index_filters(args):
    raw_status = clean_text(args.get("status", ""), "Status", max_length=20)
    return {
        "name": clean_text(args.get("name", ""), "Name", max_length=120),
        "mobile": clean_text(args.get("mobile", ""), "Mobile", max_length=20),
        "location": clean_text(args.get("location", ""), "Location", max_length=100),
        "course": clean_text(args.get("course", ""), "Course", max_length=100),
        "status": raw_status if raw_status in INQUIRY_STATUSES else "",
        "date_from": clean_text(args.get("date_from", ""), "Date from", max_length=20),
        "date_to": clean_text(args.get("date_to", ""), "Date to", max_length=20),
        "last_days": clean_text(args.get("last_days", ""), "Last days", max_length=4),
    }


def parse_sort_args(args):
    sort_col = args.get("sort", "i.inquiry_date")
    sort_dir = args.get("dir", "desc")
    if sort_col not in INQUIRY_SORT_COLUMNS:
        sort_col = "i.inquiry_date"
    if sort_dir not in {"asc", "desc"}:
        sort_dir = "desc"
    return sort_col, sort_dir


def apply_inquiry_filters(base, params, filters):
    warnings = []
    if filters["name"]:
        base += " AND i.name ILIKE %s"
        params.append(f"%{filters['name']}%")
    if filters["mobile"]:
        base += " AND i.mobile ILIKE %s"
        params.append(f"%{filters['mobile']}%")
    if filters["location"]:
        base += " AND l.name ILIKE %s"
        params.append(f"%{filters['location']}%")
    if filters["course"]:
        base += " AND c.name ILIKE %s"
        params.append(f"%{filters['course']}%")
    if filters["status"]:
        base += " AND i.status=%s"
        params.append(filters["status"])
    if filters["last_days"]:
        try:
            base += " AND i.inquiry_date >= %s"
            params.append(date.today() - timedelta(days=int(filters["last_days"])))
        except ValueError:
            warnings.append("Last X Days must be a valid number.")
    if filters["date_from"]:
        base += " AND i.inquiry_date >= %s"
        params.append(filters["date_from"])
    if filters["date_to"]:
        base += " AND i.inquiry_date <= %s"
        params.append(filters["date_to"])
    return base, params, warnings


def load_index_lookups(cur, role, loc_id):
    if role == "teacher" and loc_id:
        cur.execute("SELECT id,name FROM locations WHERE id=%s ORDER BY position,name;", (loc_id,))
        locations = cur.fetchall()
        cur.execute("SELECT id,name FROM courses WHERE location_id=%s ORDER BY position,name;", (loc_id,))
        courses = cur.fetchall()
    else:
        cur.execute("SELECT id,name FROM locations ORDER BY position,name;")
        locations = cur.fetchall()
        cur.execute("SELECT id,name FROM courses ORDER BY position,name;")
        courses = cur.fetchall()
    return locations, courses


def load_form_options(cur, role, assigned_loc_id):
    if role == "teacher" and assigned_loc_id:
        cur.execute("SELECT id,name FROM locations WHERE id=%s ORDER BY position,name;", (assigned_loc_id,))
        locations = cur.fetchall()
        cur.execute("SELECT id,name,fees FROM courses WHERE location_id=%s ORDER BY position,name;", (assigned_loc_id,))
        courses = cur.fetchall()
        cur.execute(
            "SELECT id,name,discount_type,discount_value FROM offers "
            "WHERE is_active=TRUE AND (valid_to IS NULL OR valid_to >= CURRENT_DATE) "
            "AND (location_id IS NULL OR location_id=%s) ORDER BY name;",
            (assigned_loc_id,),
        )
    else:
        cur.execute("SELECT id,name FROM locations ORDER BY position,name;")
        locations = cur.fetchall()
        cur.execute("SELECT id,name,fees FROM courses ORDER BY position,name;")
        courses = cur.fetchall()
        cur.execute(
            "SELECT id,name,discount_type,discount_value FROM offers "
            "WHERE is_active=TRUE AND (valid_to IS NULL OR valid_to >= CURRENT_DATE) ORDER BY name;"
        )
    offers = cur.fetchall()
    return locations, courses, offers


def validate_teacher_form_access(cur, course_id, offer_id, assigned_loc_id):
    if course_id:
        cur.execute("SELECT 1 FROM courses WHERE id=%s AND location_id=%s;", (course_id, assigned_loc_id))
        if not cur.fetchone():
            raise ValueError("You can only use courses from your assigned location.")
    if offer_id:
        cur.execute(
            "SELECT 1 FROM offers WHERE id=%s AND (location_id IS NULL OR location_id=%s);",
            (offer_id, assigned_loc_id),
        )
        if not cur.fetchone():
            raise ValueError("You can only use offers available to your assigned location.")


def fetch_inquiry(cur, iid, role, loc_id, with_joins=False):
    select_sql = "i.*"
    joins_sql = ""
    if with_joins:
        select_sql = "i.*, l.name AS location_name, c.name AS course_name"
        joins_sql = (
            " LEFT JOIN locations l ON i.location_id=l.id"
            " LEFT JOIN courses c ON i.course_id=c.id"
        )

    query = f"SELECT {select_sql} FROM inquiries i{joins_sql} WHERE i.id=%s"
    params = [iid]
    if role == "teacher" and loc_id:
        query += " AND i.location_id=%s"
        params.append(loc_id)
    cur.execute(query + ";", params)
    return cur.fetchone()


def normalize_mobile(value):
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) != 10:
        raise ValueError("Mobile must be a valid 10-digit number.")
    return digits


def normalize_optional_mobile(value, field_name):
    return clean_optional_text(value, field_name, max_length=20)


def render_inquiry_form(*, inquiry, locations, courses, offers, defaults, action, form_data=None, form_error_popup=None):
    return render_template(
        "inquiries/form.html",
        inquiry=inquiry,
        locations=locations,
        courses=courses,
        offers=offers,
        defaults=defaults,
        action=action,
        form_data=form_data or {},
        form_error_popup=form_error_popup,
    )


def parse_amount(value, field_name):
    raw = str(value or "0").replace(",", "").strip()
    try:
        amount = float(raw or 0)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid number.") from exc
    if amount < 0:
        raise ValueError(f"{field_name} cannot be negative.")
    return amount


def parse_date(value, field_name, required=False):
    raw = (value or "").strip()
    if not raw:
        if required:
            raise ValueError(f"{field_name} is required.")
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid date.") from exc


def validate_inquiry_form(form, fees_total):
    name = clean_text(form.get("name"), "Name", required=True, max_length=120)
    mobile = normalize_mobile(form.get("mobile"))
    inquiry_date = parse_date(form.get("inquiry_date"), "Inquiry date", required=True)
    followup_date = parse_date(form.get("followup_date"), "Follow-up date")
    admission_date = parse_date(form.get("admission_date"), "Admission date")
    fees_paid = parse_amount(form.get("fees_paid", "0"), "Fees paid")
    gender = clean_choice(form.get("gender"), "Gender", {"Male", "Female", "Other"}, required=False)
    status = clean_choice(form.get("status", "Open"), "Status", INQUIRY_STATUSES)
    city = clean_optional_text(form.get("city"), "City", max_length=80)
    state = clean_optional_text(form.get("state"), "State", max_length=80)
    ref1_name = clean_optional_text(form.get("ref1_name"), "Reference 1 name", max_length=100)
    ref2_name = clean_optional_text(form.get("ref2_name"), "Reference 2 name", max_length=100)
    ref3_name = clean_optional_text(form.get("ref3_name"), "Reference 3 name", max_length=100)
    ref1_mobile = normalize_optional_mobile(form.get("ref1_mobile"), "Reference 1 mobile")
    ref2_mobile = normalize_optional_mobile(form.get("ref2_mobile"), "Reference 2 mobile")
    ref3_mobile = normalize_optional_mobile(form.get("ref3_mobile"), "Reference 3 mobile")

    if followup_date and followup_date < inquiry_date:
        raise ValueError("Follow-up date cannot be earlier than inquiry date.")
    if admission_date and admission_date < inquiry_date:
        raise ValueError("Admission date cannot be earlier than inquiry date.")
    if fees_paid > fees_total:
        raise ValueError("Fees paid cannot be greater than total fees.")

    return {
        "name": name,
        "mobile": mobile,
        "gender": gender,
        "status": status,
        "city": city,
        "state": state,
        "inquiry_date": inquiry_date.isoformat(),
        "followup_date": followup_date.isoformat() if followup_date else None,
        "admission_date": admission_date.isoformat() if admission_date else None,
        "fees_paid": fees_paid,
        "ref1_name": ref1_name,
        "ref1_mobile": ref1_mobile,
        "ref2_name": ref2_name,
        "ref2_mobile": ref2_mobile,
        "ref3_name": ref3_name,
        "ref3_mobile": ref3_mobile,
    }


def calculate_total_fees(course_id, offer_id):
    if not course_id:
        return 0.0

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT fees FROM courses WHERE id=%s;", (course_id,))
        row = cur.fetchone()
        fees_total = float(row["fees"]) if row else 0.0
        if offer_id:
            cur.execute("SELECT discount_type,discount_value FROM offers WHERE id=%s;", (offer_id,))
            offer = cur.fetchone()
            if offer:
                if offer["discount_type"] == "percent":
                    fees_total -= fees_total * float(offer["discount_value"]) / 100
                else:
                    fees_total -= float(offer["discount_value"])
        return max(0.0, fees_total)
    finally:
        close_db(conn, commit=False)
