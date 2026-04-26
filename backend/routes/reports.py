"""
routes/reports.py - Reports and analytics
"""
from datetime import date

from flask import Blueprint, jsonify, render_template, request, session

from database import close_db, get_db
from routes.auth import login_required, role_required
from validation import parse_optional_date

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")

_STATUS_ORDER = ("Open", "Converted", "Closed")


def _parse_report_dates():
    today = date.today()
    default_from = date(today.year, 1, 1)
    d_from = parse_optional_date(request.args.get("from"), "From date") or default_from
    d_to = parse_optional_date(request.args.get("to"), "To date") or today
    if d_from > d_to:
        raise ValueError("From date cannot be later than To date.")
    return d_from, d_to


def _teacher_scope():
    role = session.get("role")
    loc_id = session.get("location_id")
    if role == "teacher" and loc_id:
        return " AND i.location_id=%s", [loc_id]
    return "", []


@reports_bp.route("/")
@login_required
@role_required("admin", "developer", "teacher")
def index():
    return render_template("reports/index.html")


@reports_bp.route("/data")
@login_required
@role_required("admin", "developer", "teacher")
def data():
    try:
        d_from, d_to = _parse_report_dates()
    except ValueError as exc:
        return jsonify({"ok": False, "msg": str(exc)}), 400

    lc, lp = _teacher_scope()

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        f"""
        WITH months AS (
            SELECT generate_series(
                date_trunc('month', %s::date),
                date_trunc('month', %s::date),
                interval '1 month'
            )::date AS month_start
        )
        SELECT
            TO_CHAR(months.month_start, 'YYYY-MM') AS month,
            COALESCE(COUNT(i.id), 0) AS inquiries,
            COALESCE(SUM(CASE WHEN i.status='Converted' THEN 1 ELSE 0 END), 0) AS admissions
        FROM months
        LEFT JOIN inquiries i
            ON date_trunc('month', i.inquiry_date) = months.month_start
           AND i.inquiry_date BETWEEN %s AND %s
           {lc}
        GROUP BY months.month_start
        ORDER BY months.month_start;
        """,
        [d_from, d_to, d_from, d_to] + lp,
    )
    trend = [dict(row) for row in cur.fetchall()]

    cur.execute(
        f"""
        SELECT status, COUNT(*) AS total
        FROM inquiries i
        WHERE inquiry_date BETWEEN %s AND %s {lc}
        GROUP BY status;
        """,
        [d_from, d_to] + lp,
    )
    raw_status = {row["status"]: int(row["total"] or 0) for row in cur.fetchall()}
    status_data = [{"status": status, "total": raw_status.get(status, 0)} for status in _STATUS_ORDER]

    cur.execute(
        f"""
        SELECT
            COALESCE(l.name, 'Unknown') AS location,
            COUNT(*) AS inquiries,
            COALESCE(SUM(CASE WHEN i.status='Converted' THEN 1 ELSE 0 END), 0) AS admissions,
            COALESCE(SUM(i.fees_paid), 0) AS revenue
        FROM inquiries i
        LEFT JOIN locations l ON i.location_id=l.id
        WHERE i.inquiry_date BETWEEN %s AND %s {lc}
        GROUP BY l.id, l.name
        ORDER BY inquiries DESC, location ASC;
        """,
        [d_from, d_to] + lp,
    )
    location_data = [dict(row) for row in cur.fetchall()]

    cur.execute(
        f"""
        SELECT
            COALESCE(c.name, 'Unknown') AS course,
            COUNT(*) AS inquiries,
            COALESCE(SUM(CASE WHEN i.status='Converted' THEN 1 ELSE 0 END), 0) AS admissions,
            COALESCE(SUM(i.fees_paid), 0) AS revenue
        FROM inquiries i
        LEFT JOIN courses c ON i.course_id=c.id
        WHERE i.inquiry_date BETWEEN %s AND %s {lc}
        GROUP BY c.id, c.name
        ORDER BY inquiries DESC, course ASC
        LIMIT 10;
        """,
        [d_from, d_to] + lp,
    )
    course_data = [dict(row) for row in cur.fetchall()]

    cur.execute(
        f"""
        SELECT
            COUNT(*) AS total,
            COALESCE(SUM(CASE WHEN status='Converted' THEN 1 ELSE 0 END), 0) AS converted,
            COALESCE(SUM(fees_paid), 0) AS revenue,
            COALESCE(SUM(CASE WHEN status='Converted' THEN fees_total-fees_paid ELSE 0 END), 0) AS pending
        FROM inquiries i
        WHERE inquiry_date BETWEEN %s AND %s {lc};
        """,
        [d_from, d_to] + lp,
    )
    summary = dict(cur.fetchone() or {})

    close_db(conn, commit=False)
    return jsonify(
        {
            "ok": True,
            "trend": trend,
            "status": status_data,
            "location": location_data,
            "course": course_data,
            "summary": summary,
            "from": d_from.isoformat(),
            "to": d_to.isoformat(),
        }
    )
