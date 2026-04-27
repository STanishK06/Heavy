"""
routes/whatsapp.py - WhatsApp template management
"""
from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for

from database import close_db, get_db
from routes.auth import login_required, role_required
from validation import clean_optional_text, clean_text

whatsapp_bp = Blueprint("whatsapp", __name__, url_prefix="/whatsapp")


def _validate_template_form(form):
    return {
        "name": clean_text(form.get("name"), "Template name", required=True, max_length=100),
        "description": clean_optional_text(form.get("description"), "Description", max_length=2000, multiline=True),
    }


@whatsapp_bp.route("/")
@login_required
@role_required("admin", "developer", "teacher")
def index():
    q = clean_text(request.args.get("q", ""), "Search", max_length=100)
    msgs = []

    try:
        conn = get_db()
        cur = conn.cursor()
        sql = "SELECT * FROM whatsapp_msgs WHERE 1=1"
        params = []
        if q:
            sql += " AND (name ILIKE %s OR description ILIKE %s)"
            params += [f"%{q}%", f"%{q}%"]
        sql += " ORDER BY created_at DESC;"
        cur.execute(sql, params)
        msgs = cur.fetchall()
        close_db(conn, commit=False)
    except Exception:
        current_app.logger.exception("Failed to load WhatsApp templates page")
        flash("Unable to load WhatsApp templates right now.", "danger")

    return render_template("whatsapp/index.html", msgs=msgs, q=q)


@whatsapp_bp.route("/add", methods=["GET", "POST"])
@login_required
@role_required("admin", "developer")
def add():
    if request.method == "POST":
        try:
            cleaned = _validate_template_form(request.form)
            conn = get_db()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO whatsapp_msgs (name,description) VALUES (%s,%s);",
                (cleaned["name"], cleaned["description"]),
            )
            close_db(conn)
            flash("Template saved.", "success")
            return redirect(url_for("whatsapp.index"))
        except ValueError as exc:
            flash(str(exc), "danger")
        except Exception:
            current_app.logger.exception("Failed to save WhatsApp template")
            flash("Unable to save the template right now.", "danger")

    return render_template("whatsapp/form.html", msg=None, action="Add")


@whatsapp_bp.route("/<int:mid>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin", "developer")
def edit(mid):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM whatsapp_msgs WHERE id=%s;", (mid,))
        msg = cur.fetchone()
        close_db(conn, commit=False)
    except Exception:
        current_app.logger.exception("Failed to load WhatsApp template %s", mid)
        flash("Unable to load the template right now.", "danger")
        return redirect(url_for("whatsapp.index"))

    if not msg:
        flash("Not found.", "danger")
        return redirect(url_for("whatsapp.index"))

    if request.method == "POST":
        try:
            cleaned = _validate_template_form(request.form)
            conn = get_db()
            cur = conn.cursor()
            cur.execute(
                "UPDATE whatsapp_msgs SET name=%s,description=%s WHERE id=%s;",
                (cleaned["name"], cleaned["description"], mid),
            )
            close_db(conn)
            flash("Updated.", "success")
            return redirect(url_for("whatsapp.index"))
        except ValueError as exc:
            flash(str(exc), "danger")
        except Exception:
            current_app.logger.exception("Failed to update WhatsApp template %s", mid)
            flash("Unable to update the template right now.", "danger")

    return render_template("whatsapp/form.html", msg=msg, action="Edit")


@whatsapp_bp.route("/<int:mid>/delete", methods=["POST"])
@login_required
@role_required("admin", "developer")
def delete(mid):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM whatsapp_msgs WHERE id=%s;", (mid,))
        close_db(conn)
        flash("Deleted.", "success")
    except Exception:
        current_app.logger.exception("Failed to delete WhatsApp template %s", mid)
        flash("Unable to delete the template right now.", "danger")
    return redirect(url_for("whatsapp.index"))


@whatsapp_bp.route("/api/templates")
@login_required
def api_templates():
    if session.get("role") not in {"admin", "developer"}:
        return jsonify({"ok": False, "msg": "Permission denied."}), 403

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id,name,description FROM whatsapp_msgs ORDER BY name;")
        msgs = [dict(row) for row in cur.fetchall()]
        close_db(conn, commit=False)
        return jsonify({"ok": True, "templates": msgs})
    except Exception:
        current_app.logger.exception("Failed to load WhatsApp templates API")
        return jsonify({"ok": False, "msg": "Templates are temporarily unavailable."}), 503
