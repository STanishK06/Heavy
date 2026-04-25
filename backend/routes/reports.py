"""
routes/reports.py — Reports & Analytics
"""
from flask import Blueprint, render_template, request, jsonify, session
from database import get_db, close_db
from routes.auth import login_required, role_required
from datetime import date

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")

@reports_bp.route("/")
@login_required
@role_required("admin","developer","teacher")
def index():
    return render_template("reports/index.html")

@reports_bp.route("/data")
@login_required
@role_required("admin","developer","teacher")
def data():
    role   = session.get("role"); loc_id = session.get("location_id")
    d_from = request.args.get("from", f"{date.today().year}-01-01")
    d_to   = request.args.get("to",   date.today().isoformat())

    lc, lp = ("", []) if role != "teacher" or not loc_id else (" AND i.location_id=%s", [loc_id])

    conn = get_db(); cur = conn.cursor()

    # Inquiries vs Admissions trend (monthly)
    cur.execute(f"""
        SELECT TO_CHAR(inquiry_date,'YYYY-MM') AS month,
               COUNT(*) AS inquiries,
               SUM(CASE WHEN status='Converted' THEN 1 ELSE 0 END) AS admissions
        FROM inquiries i WHERE inquiry_date BETWEEN %s AND %s {lc}
        GROUP BY month ORDER BY month;
    """, [d_from, d_to]+lp)
    trend = cur.fetchall()

    # Status breakdown
    cur.execute(f"""
        SELECT status, COUNT(*) AS total FROM inquiries i
        WHERE inquiry_date BETWEEN %s AND %s {lc} GROUP BY status;
    """, [d_from, d_to]+lp)
    status_data = cur.fetchall()

    # Location performance
    cur.execute(f"""
        SELECT l.name AS location, COUNT(*) AS inquiries,
               SUM(CASE WHEN i.status='Converted' THEN 1 ELSE 0 END) AS admissions,
               COALESCE(SUM(i.fees_paid),0) AS revenue
        FROM inquiries i LEFT JOIN locations l ON i.location_id=l.id
        WHERE i.inquiry_date BETWEEN %s AND %s {lc}
        GROUP BY l.name ORDER BY inquiries DESC;
    """, [d_from, d_to]+lp)
    location_data = cur.fetchall()

    # Course performance
    cur.execute(f"""
        SELECT c.name AS course, COUNT(*) AS inquiries,
               SUM(CASE WHEN i.status='Converted' THEN 1 ELSE 0 END) AS admissions,
               COALESCE(SUM(i.fees_paid),0) AS revenue
        FROM inquiries i LEFT JOIN courses c ON i.course_id=c.id
        WHERE i.inquiry_date BETWEEN %s AND %s {lc}
        GROUP BY c.name ORDER BY inquiries DESC LIMIT 10;
    """, [d_from, d_to]+lp)
    course_data = cur.fetchall()

    # Summary
    cur.execute(f"""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN status='Converted' THEN 1 ELSE 0 END) AS converted,
               COALESCE(SUM(fees_paid),0) AS revenue,
               COALESCE(SUM(CASE WHEN status='Converted' THEN fees_total-fees_paid ELSE 0 END),0) AS pending
        FROM inquiries i WHERE inquiry_date BETWEEN %s AND %s {lc};
    """, [d_from, d_to]+lp)
    summary = cur.fetchone()

    close_db(conn, commit=False)
    return jsonify({
        "trend":    [dict(r) for r in trend],
        "status":   [dict(r) for r in status_data],
        "location": [dict(r) for r in location_data],
        "course":   [dict(r) for r in course_data],
        "summary":  dict(summary) if summary else {},
        "from": d_from, "to": d_to
    })
