"""
routes/auth.py — Authentication (HeavyLift CRM)
Only admin/developer roles. Account creation restricted to logged-in admins/devs.
Developers can change any account's password.
"""
from collections import defaultdict, deque
from datetime import datetime, timedelta
from threading import Lock

from flask import Blueprint, current_app, render_template, request, redirect, url_for, session, flash, jsonify, make_response

from config import Config
from database import get_db, close_db
from security import build_session_fingerprint, hash_password, is_lock_active, needs_password_rehash, verify_password
from validation import clean_choice, clean_email, clean_text, clean_username, parse_optional_int
from functools import wraps

auth_bp = Blueprint("auth", __name__)
_login_attempts_by_ip = defaultdict(deque)
_login_attempts_lock = Lock()

# ── decorators ────────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def dec(*a, **kw):
        if "user_id" not in session:
            flash("Please log in.", "warning")
            return redirect(url_for("auth.login"))
        return f(*a, **kw)
    return dec

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def dec(*a, **kw):
            if session.get("role") not in roles:
                flash("Access denied.", "danger")
                return redirect(url_for("dashboard"))
            return f(*a, **kw)
        return dec
    return decorator


def _client_ip():
    return (request.access_route[0] if request.access_route else request.remote_addr or "unknown")[:64]


def _session_fingerprint(client_ip):
    return build_session_fingerprint(client_ip, request.user_agent.string or "")


def _prune_ip_attempts(attempts, now):
    window_start = now - timedelta(seconds=Config.LOGIN_RATE_LIMIT_WINDOW_SECONDS)
    while attempts and attempts[0] < window_start:
        attempts.popleft()


def _is_ip_rate_limited(ip, now):
    with _login_attempts_lock:
        attempts = _login_attempts_by_ip[ip]
        _prune_ip_attempts(attempts, now)
        return len(attempts) >= Config.LOGIN_RATE_LIMIT_MAX_ATTEMPTS


def _record_ip_failure(ip, now):
    with _login_attempts_lock:
        attempts = _login_attempts_by_ip[ip]
        _prune_ip_attempts(attempts, now)
        attempts.append(now)


def _clear_ip_failures(ip):
    with _login_attempts_lock:
        _login_attempts_by_ip.pop(ip, None)


def _reset_login_security_state():
    with _login_attempts_lock:
        _login_attempts_by_ip.clear()


def _validate_password(password):
    if len(password or "") < 8:
        raise ValueError("Password must be at least 8 characters.")
    return password


def _honeypot_triggered():
    return bool((request.form.get("website") or "").strip())


def _lockout_response():
    flash("Too many login attempts. Please try again later.", "danger")
    response = make_response(render_template("login.html"), 429)
    return _set_no_store_headers(response)


def _set_no_store_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# ── login ─────────────────────────────────────────────────────────────────────
@auth_bp.route("/", methods=["GET","POST"])
@auth_bp.route("/login", methods=["GET","POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        password = request.form.get("password", "")
        client_ip = _client_ip()
        now = datetime.now()

        if _honeypot_triggered():
            _record_ip_failure(client_ip, now)
            current_app.logger.warning("Login honeypot triggered from %s", client_ip)
            flash("Invalid credentials.", "danger")
            response = make_response(render_template("login.html"), 400)
            return _set_no_store_headers(response)

        try:
            username = clean_text(request.form.get("username", ""), "Username", required=True, max_length=80)
        except ValueError:
            _record_ip_failure(client_ip, now)
            flash("Invalid credentials.", "danger")
            return _set_no_store_headers(make_response(render_template("login.html")))

        if _is_ip_rate_limited(client_ip, now):
            return _lockout_response()

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username=%s;", (username,))
        user = cur.fetchone()

        if user and is_lock_active(user.get("locked_until"), now):
            close_db(conn, commit=False)
            _record_ip_failure(client_ip, now)
            return _lockout_response()

        try:
            password_ok = bool(user and verify_password(user["password_hash"], password))
        except RuntimeError:
            close_db(conn, commit=False)
            current_app.logger.exception("Authentication backend is unavailable.")
            flash("Authentication is temporarily unavailable.", "danger")
            response = make_response(render_template("login.html"), 503)
            return _set_no_store_headers(response)

        if password_ok:
            updated_hash = hash_password(password) if needs_password_rehash(user["password_hash"]) else user["password_hash"]
            cur.execute(
                """
                UPDATE users
                SET password_hash=%s,
                    failed_login_attempts=0,
                    locked_until=NULL,
                    last_failed_login_at=NULL
                WHERE id=%s;
                """,
                (updated_hash, user["id"]),
            )
            close_db(conn)
            _clear_ip_failures(client_ip)
            session.clear()
            session.permanent = True
            session["user_id"]     = user["id"]
            session["username"]    = user["username"]
            session["role"]        = user["role"]
            session["location_id"] = user["location_id"]
            session["login_ip"]    = client_ip
            session["login_ua"]    = (request.user_agent.string or "")[:255]
            session["session_fingerprint"] = _session_fingerprint(client_ip)
            return redirect(url_for("dashboard"))

        if user:
            failed_attempts = int(user.get("failed_login_attempts") or 0) + 1
            locked_until = None
            if failed_attempts >= Config.LOGIN_LOCKOUT_THRESHOLD:
                locked_until = now + timedelta(minutes=Config.LOGIN_LOCKOUT_MINUTES)
            cur.execute(
                """
                UPDATE users
                SET failed_login_attempts=%s,
                    locked_until=%s,
                    last_failed_login_at=%s
                WHERE id=%s;
                """,
                (failed_attempts, locked_until, now, user["id"]),
            )
            close_db(conn)
        else:
            close_db(conn, commit=False)

        _record_ip_failure(client_ip, now)
        flash("Invalid credentials.", "danger")
    return _set_no_store_headers(make_response(render_template("login.html")))

# ── create account (admin/dev only, must be logged in) ────────────────────────
@auth_bp.route("/users/create", methods=["GET","POST"])
@login_required
@role_required("admin","developer")
def create_user():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id,name FROM locations ORDER BY position,name;")
    locations = cur.fetchall(); close_db(conn, commit=False)

    if request.method == "POST":
        try:
            username = clean_username(request.form.get("username"))
            email = clean_email(request.form.get("email"))
            password = _validate_password(request.form.get("password", ""))
            confirm = request.form.get("confirm_password", "")
            role = clean_choice(request.form.get("role", "teacher"), "Role", {"teacher", "admin", "developer"})
            loc_id = parse_optional_int(request.form.get("location_id"), "Location")

            if password != confirm:
                raise ValueError("Passwords do not match.")
            if role == "developer" and session.get("role") != "developer":
                raise ValueError("Only developers can create developer accounts.")

            conn = get_db(); cur = conn.cursor()
            cur.execute("""
                INSERT INTO users (username,email,password_hash,role,location_id)
                VALUES (%s,%s,%s,%s,%s);
            """, (username, email, hash_password(password), role, loc_id))
            close_db(conn)
            flash(f"Account '{username}' created.","success")
            return redirect(url_for("users.index"))
        except ValueError as exc:
            flash(str(exc), "danger")
        except Exception:
            current_app.logger.exception("Failed to create account for %s", request.form.get("username", ""))
            close_db(conn,commit=False)
            flash("Unable to create the account right now.", "danger")

    return render_template("users/create.html", locations=locations)

# ── change password (developer can change any; admin can change own) ──────────
@auth_bp.route("/users/<int:uid>/change-password", methods=["POST"])
@login_required
def change_password(uid):
    role = session.get("role")
    current_uid = session.get("user_id")

    # Developers can change any account. Everyone else can change only their own.
    if role != "developer" and uid != current_uid:
        return jsonify({"ok": False, "msg": "Permission denied."}), 403

    payload = request.get_json(silent=True) or {}
    new_pass = payload.get("new_password","") if request.is_json else request.form.get("new_password","")
    try:
        new_pass = _validate_password(new_pass)
    except ValueError as exc:
        if request.is_json:
            return jsonify({"ok":False,"msg":str(exc)})
        flash(str(exc),"danger")
        return redirect(url_for("users.index"))

    conn = get_db(); cur = conn.cursor()
    cur.execute("UPDATE users SET password_hash=%s WHERE id=%s;",
                (hash_password(new_pass), uid))
    close_db(conn)
    if request.is_json: return jsonify({"ok":True,"msg":"Password updated."})
    flash("Password changed.","success")
    return redirect(url_for("users.index"))

# ── logout ────────────────────────────────────────────────────────────────────
@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    return _set_no_store_headers(redirect(url_for("auth.login")))
