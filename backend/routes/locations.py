"""
routes/locations.py — Locations with drag-order & analytics
"""
from flask import Blueprint, current_app, render_template, request, redirect, url_for, flash, jsonify, session
from database import get_db, close_db
from routes.auth import login_required, role_required
from validation import clean_optional_text, clean_text, validate_ordered_ids

locations_bp = Blueprint("locations", __name__, url_prefix="/locations")


def _validate_location_form(form):
    return {
        "name": clean_text(form.get("name"), "Location name", required=True, max_length=100),
        "description": clean_optional_text(form.get("description"), "Description", max_length=1000, multiline=True),
    }


def _render_location_form(*, location, action, form_data=None, form_error_popup=None):
    return render_template(
        "locations/form.html",
        location=location,
        action=action,
        form_data=form_data or {},
        form_error_popup=form_error_popup,
    )

@locations_bp.route("/")
@login_required
def index():
    search = clean_text(request.args.get("q",""), "Search", max_length=100)
    role = session.get("role")
    assigned_loc_id = session.get("location_id")
    conn = get_db(); cur = conn.cursor()
    q = "SELECT * FROM locations WHERE 1=1"
    p = []
    if role == "teacher" and assigned_loc_id:
        q += " AND id=%s"
        p.append(assigned_loc_id)
    if search:
        q += " AND (name ILIKE %s OR description ILIKE %s)"
        p += [f"%{search}%", f"%{search}%"]
    q += " ORDER BY position, created_at;"
    cur.execute(q, p)
    locations = cur.fetchall(); close_db(conn, commit=False)
    return render_template("locations/index.html", locations=locations, search=search)

@locations_bp.route("/add", methods=["GET","POST"])
@login_required
@role_required("admin","developer")
def add():
    if request.method == "POST":
        conn = get_db(); cur = conn.cursor()
        try:
            cleaned = _validate_location_form(request.form)
            cur.execute("SELECT COALESCE(MAX(position),0)+1 AS next_position FROM locations;")
            pos = cur.fetchone()["next_position"]
            cur.execute("INSERT INTO locations (name,description,position) VALUES (%s,%s,%s);", (cleaned["name"], cleaned["description"], pos))
            close_db(conn); flash(f"Location '{cleaned['name']}' created.","success")
            return redirect(url_for("locations.index"))
        except ValueError as exc:
            close_db(conn,commit=False); flash(str(exc),"danger")
            return _render_location_form(
                location=None,
                action="Add",
                form_data=request.form.to_dict(flat=True),
                form_error_popup=str(exc),
            )
        except Exception:
            current_app.logger.exception("Failed to create location")
            close_db(conn,commit=False)
            message = "Unable to create the location right now."
            flash(message,"danger")
            return _render_location_form(
                location=None,
                action="Add",
                form_data=request.form.to_dict(flat=True),
                form_error_popup=message,
            )
    return _render_location_form(location=None, action="Add")

@locations_bp.route("/<int:loc_id>/edit", methods=["GET","POST"])
@login_required
@role_required("admin","developer")
def edit(loc_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM locations WHERE id=%s;", (loc_id,))
    location = cur.fetchone(); close_db(conn, commit=False)
    if not location: flash("Not found.","danger"); return redirect(url_for("locations.index"))
    if request.method == "POST":
        try:
            cleaned = _validate_location_form(request.form)
            conn = get_db(); cur = conn.cursor()
            cur.execute("UPDATE locations SET name=%s,description=%s WHERE id=%s;", (cleaned["name"], cleaned["description"], loc_id))
            close_db(conn); flash("Updated.","success"); return redirect(url_for("locations.index"))
        except ValueError as exc:
            flash(str(exc),"danger")
            return _render_location_form(
                location=location,
                action="Edit",
                form_data=request.form.to_dict(flat=True),
                form_error_popup=str(exc),
            )
        except Exception:
            current_app.logger.exception("Failed to update location %s", loc_id)
            close_db(conn,commit=False)
            message = "Unable to update the location right now."
            flash(message,"danger")
            return _render_location_form(
                location=location,
                action="Edit",
                form_data=request.form.to_dict(flat=True),
                form_error_popup=message,
            )
    return _render_location_form(location=location, action="Edit")

@locations_bp.route("/<int:loc_id>/delete", methods=["POST"])
@login_required
@role_required("admin","developer")
def delete(loc_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM locations WHERE id=%s;", (loc_id,))
    close_db(conn); flash("Deleted.","success"); return redirect(url_for("locations.index"))

@locations_bp.route("/reorder", methods=["POST"])
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
    for pos, lid in enumerate(ids):
        cur.execute("UPDATE locations SET position=%s WHERE id=%s;", (pos, lid))
    close_db(conn); return jsonify({"ok": True})

@locations_bp.route("/<int:loc_id>/analytics")
@login_required
def analytics(loc_id):
    role = session.get("role")
    assigned_loc_id = session.get("location_id")
    if role == "teacher" and assigned_loc_id and loc_id != assigned_loc_id:
        flash("Access denied.", "danger")
        return redirect(url_for("locations.index"))

    conn = get_db(); cur = conn.cursor()

    cur.execute("SELECT * FROM locations WHERE id=%s;", (loc_id,))
    location = cur.fetchone()
    if not location: close_db(conn,commit=False); flash("Not found.","danger"); return redirect(url_for("locations.index"))

    # Courses at this location
    cur.execute("SELECT * FROM courses WHERE location_id=%s ORDER BY position,name;", (loc_id,))
    courses = cur.fetchall()

    # Inquiry stats
    cur.execute("""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN status='Converted' THEN 1 ELSE 0 END) AS enrolled,
               SUM(CASE WHEN status='Open'      THEN 1 ELSE 0 END) AS open,
               SUM(CASE WHEN status='Closed'    THEN 1 ELSE 0 END) AS closed,
               COALESCE(SUM(fees_paid),0)  AS revenue,
               COALESCE(SUM(CASE WHEN status='Converted' THEN fees_total-fees_paid ELSE 0 END),0) AS pending
        FROM inquiries WHERE location_id=%s;
    """, (loc_id,))
    stats = cur.fetchone()

    # Monthly trend
    cur.execute("""
        SELECT TO_CHAR(inquiry_date,'YYYY-MM') AS month, COUNT(*) AS inquiries,
               SUM(CASE WHEN status='Converted' THEN 1 ELSE 0 END) AS admissions
        FROM inquiries WHERE location_id=%s
        GROUP BY month ORDER BY month DESC LIMIT 12;
    """, (loc_id,))
    trend = list(reversed(cur.fetchall()))

    # Recent inquiries
    cur.execute("""
        SELECT i.*, c.name AS course_name
        FROM inquiries i LEFT JOIN courses c ON i.course_id=c.id
        WHERE i.location_id=%s ORDER BY i.inquiry_date DESC LIMIT 20;
    """, (loc_id,))
    inquiries = cur.fetchall()

    close_db(conn, commit=False)
    return render_template("locations/analytics.html",
                           location=location, courses=courses,
                           stats=stats, trend=trend, inquiries=inquiries)
