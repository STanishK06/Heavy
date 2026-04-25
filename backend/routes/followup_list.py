"""
routes/followup_list.py â€” Follow-up List Page
Lists all inquiries with pending follow-up dates.
"""
from datetime import date

from flask import Blueprint, render_template, request, session

from database import close_db, get_db
from routes.auth import login_required

followup_bp = Blueprint("followup_list", __name__, url_prefix="/followups")


@followup_bp.route("/")
@login_required
def index():
    role = session.get("role")
    loc_id = session.get("location_id")
    view = request.args.get("view", "today")  # today | overdue | upcoming | all

    base = """
        SELECT i.*, l.name AS location_name, c.name AS course_name
        FROM inquiries i
        LEFT JOIN locations l ON i.location_id=l.id
        LEFT JOIN courses c ON i.course_id=c.id
        WHERE i.status='Open' AND i.followup_date IS NOT NULL
    """
    params = []
    if role == "teacher" and loc_id:
        base += " AND i.location_id=%s"
        params.append(loc_id)

    today = date.today().isoformat()
    if view == "today":
        base += " AND i.followup_date = %s"
        params.append(today)
    elif view == "overdue":
        base += " AND i.followup_date < %s"
        params.append(today)
    elif view == "upcoming":
        base += " AND i.followup_date > %s"
        params.append(today)

    base += " ORDER BY i.followup_date ASC;"

    conn = get_db()
    cur = conn.cursor()
    cur.execute(base, params)
    inquiries = cur.fetchall()
    count_query = """
        SELECT
            COUNT(*) FILTER (WHERE i.followup_date = %s) AS today,
            COUNT(*) FILTER (WHERE i.followup_date < %s) AS overdue,
            COUNT(*) FILTER (WHERE i.followup_date > %s) AS upcoming,
            COUNT(*) AS all
        FROM inquiries i
        WHERE i.status='Open' AND i.followup_date IS NOT NULL
    """
    count_params = [today, today, today]
    if role == "teacher" and loc_id:
        count_query += " AND i.location_id=%s"
        count_params.append(loc_id)
    cur.execute(count_query, count_params)
    counts = cur.fetchone()

    close_db(conn, commit=False)
    return render_template("followup/index.html", inquiries=inquiries, view=view, counts=counts, today=today)
