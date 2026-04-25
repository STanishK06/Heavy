"""
routes/users.py — User Management (Developer/Admin view)
"""
from flask import Blueprint, current_app, render_template, request, redirect, url_for, flash, session, jsonify
from database import get_db, close_db
from routes.auth import login_required, role_required
from validation import clean_email, clean_username, parse_optional_int

users_bp = Blueprint("users", __name__, url_prefix="/users")

@users_bp.route("/")
@login_required
@role_required("admin","developer")
def index():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT u.*, l.name AS location_name
        FROM users u LEFT JOIN locations l ON u.location_id=l.id
        ORDER BY u.created_at DESC;
    """)
    users = cur.fetchall(); close_db(conn, commit=False)
    return render_template("users/index.html", users=users)

@users_bp.route("/<int:uid>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin","developer")
def edit(uid):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id=%s;", (uid,))
    user = cur.fetchone()
    cur.execute("SELECT id,name FROM locations ORDER BY position,name;")
    locations = cur.fetchall()
    close_db(conn, commit=False)
    if not user:
        flash("Not found.","danger")
        return redirect(url_for("users.index"))

    if request.method == "POST":
        try:
            username = clean_username(request.form.get("username"))
            email = clean_email(request.form.get("email"))
            location_id = parse_optional_int(request.form.get("location_id"), "Location")

            conn = get_db(); cur = conn.cursor()
            cur.execute("SELECT id FROM users WHERE username=%s AND id<>%s LIMIT 1;", (username, uid))
            if cur.fetchone():
                close_db(conn, commit=False)
                raise ValueError("Username is already in use.")
            cur.execute("SELECT id FROM users WHERE email=%s AND id<>%s LIMIT 1;", (email, uid))
            if cur.fetchone():
                close_db(conn, commit=False)
                raise ValueError("Email is already in use.")

            cur.execute(
                "UPDATE users SET username=%s,email=%s,location_id=%s WHERE id=%s;",
                (username, email, location_id, uid),
            )
            close_db(conn)

            if uid == session.get("user_id"):
                session["username"] = username
                session["location_id"] = location_id

            flash("User details updated.","success")
            return redirect(url_for("users.index"))
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_template(
                "users/edit.html",
                user=user,
                locations=locations,
                form_data=request.form.to_dict(flat=True),
                form_error_popup=str(exc),
            )
        except Exception:
            current_app.logger.exception("Failed to update user %s", uid)
            close_db(conn, commit=False)
            message = "Unable to update the user right now."
            flash(message, "danger")
            return render_template(
                "users/edit.html",
                user=user,
                locations=locations,
                form_data=request.form.to_dict(flat=True),
                form_error_popup=message,
            )

    return render_template("users/edit.html", user=user, locations=locations, form_data={})

@users_bp.route("/<int:uid>/delete", methods=["POST"])
@login_required
@role_required("developer")
def delete(uid):
    if uid == session.get("user_id"):
        flash("Cannot delete yourself.","danger")
        return redirect(url_for("users.index"))
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE id=%s;", (uid,))
    close_db(conn); flash("User deleted.","success")
    return redirect(url_for("users.index"))

@users_bp.route("/<int:uid>/role", methods=["POST"])
@login_required
@role_required("developer")
def change_role(uid):
    role = request.form.get("role")
    if role not in ("teacher","admin","developer"):
        flash("Invalid role.","danger")
        return redirect(url_for("users.index"))
    conn = get_db(); cur = conn.cursor()
    cur.execute("UPDATE users SET role=%s WHERE id=%s;", (role,uid))
    close_db(conn); flash("Role updated.","success")
    return redirect(url_for("users.index"))
