"""
app.py - HeavyLift CRM entry point
"""
from __future__ import annotations

import os
import secrets

import click
from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for
from markupsafe import Markup, escape
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from database import bootstrap_user, init_db
from rate_limit import rate_limiter
from security import build_session_fingerprint
from security_audit import build_security_audit_report

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")
TEMPLATE_DIR = os.path.join(FRONTEND_DIR, "templates")
STATIC_DIR = os.path.join(FRONTEND_DIR, "static")

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
app.config.from_object(Config)
Config.validate_runtime()

if Config.TRUST_PROXY_HEADERS:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

if Config.INIT_DB_ON_START and os.getenv("SKIP_INIT_DB") != "1":
    init_db()
    bootstrap_user()

from routes.auth import auth_bp
from routes.courses import courses_bp
from routes.followup_list import followup_bp
from routes.inquiries import inquiries_bp
from routes.locations import locations_bp
from routes.notifications import notif_bp, socketio
from routes.offers import offers_bp
from routes.reports import reports_bp
from routes.users import users_bp
from routes.whatsapp import whatsapp_bp

socketio.init_app(
    app,
    async_mode="threading",
    manage_session=False,
    ping_interval=Config.SOCKETIO_PING_INTERVAL,
    ping_timeout=Config.SOCKETIO_PING_TIMEOUT,
)

app.register_blueprint(auth_bp)
app.register_blueprint(users_bp)
app.register_blueprint(locations_bp)
app.register_blueprint(courses_bp)
app.register_blueprint(inquiries_bp)
app.register_blueprint(followup_bp)
app.register_blueprint(offers_bp)
app.register_blueprint(whatsapp_bp)
app.register_blueprint(reports_bp)
app.register_blueprint(notif_bp)

_API_RATE_LIMITS = {
    "notifications.count": Config.API_RATE_LIMIT_MAX_REQUESTS * 2,
    "notifications.list_all": Config.API_RATE_LIMIT_MAX_REQUESTS * 2,
    "notifications.snapshot": Config.API_RATE_LIMIT_MAX_REQUESTS * 2,
    "notifications.mark_read": Config.API_RATE_LIMIT_MAX_REQUESTS,
    "notifications.read_all": Config.API_RATE_LIMIT_MAX_REQUESTS,
    "offers.calculate": Config.API_RATE_LIMIT_MAX_REQUESTS,
    "whatsapp.api_templates": Config.API_RATE_LIMIT_MAX_REQUESTS,
    "inquiries.send_whatsapp": Config.MESSAGE_SEND_RATE_LIMIT_MAX_REQUESTS,
}


def _client_ip():
    return (request.access_route[0] if request.access_route else request.remote_addr or "unknown")[:64]


def _ensure_csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def _is_local_request():
    host = (request.host or "").split(":", 1)[0]
    return host in {"127.0.0.1", "localhost"}


def _wants_json_response():
    if request.is_json:
        return True
    if request.path.startswith(("/notifications/", "/offers/api/", "/whatsapp/api/")):
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json" and request.accept_mimetypes[best] > request.accept_mimetypes["text/html"]


def _error_response(status_code, message):
    if _wants_json_response():
        return jsonify({"ok": False, "msg": message}), status_code
    return render_template("error.html", code=status_code, msg=message), status_code


def _content_security_policy():
    return "; ".join(
        [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com",
            "font-src 'self' data: https://fonts.gstatic.com https://cdnjs.cloudflare.com",
            "img-src 'self' data: https:",
            "connect-src 'self' ws: wss:",
            "frame-ancestors 'self'",
            "form-action 'self'",
            "base-uri 'self'",
            "object-src 'none'",
            "upgrade-insecure-requests",
            "block-all-mixed-content",
        ]
    )


def _session_fingerprint():
    return build_session_fingerprint(_client_ip(), request.user_agent.string or "")


@app.context_processor
def inject_security_helpers():
    token = _ensure_csrf_token()
    return {
        "csrf_token": lambda: token,
        "csrf_input": lambda: Markup(
            f'<input type="hidden" name="csrf_token" value="{escape(token)}"/>'
        ),
    }


@app.cli.command("init-db")
def init_db_command():
    init_db()
    created = bootstrap_user()
    click.echo("HeavyLift CRM database ready.")
    if created:
        click.echo("Bootstrap user created from BOOTSTRAP_* environment variables.")


@app.cli.command("bootstrap-user")
@click.option("--username", prompt=True)
@click.option("--email", prompt=True)
@click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
@click.option(
    "--role",
    type=click.Choice(["teacher", "admin", "developer"]),
    default="developer",
    show_default=True,
)
def bootstrap_user_command(username, email, password, role):
    init_db()
    created = bootstrap_user(username=username, email=email, password=password, role=role)
    if created:
        click.echo(f"User '{username}' created.")
    else:
        click.echo("A user with that username or email already exists.")


@app.cli.command("security-audit")
def security_audit_command():
    report, exit_code = build_security_audit_report(os.path.dirname(BASE_DIR))
    click.echo(report)
    if exit_code:
        raise SystemExit(exit_code)


@app.before_request
def force_https():
    if not Config.HTTPS_REDIRECT or Config.DEBUG:
        return None
    if request.is_secure:
        return None
    if _is_local_request() and not (Config.SSL_CERT_FILE and Config.SSL_KEY_FILE):
        return None
    return redirect(request.url.replace("http://", "https://", 1), code=301)


@app.before_request
def protect_session():
    if "user_id" not in session:
        return None

    expected = session.get("session_fingerprint")
    current = _session_fingerprint()
    if expected and current and not secrets.compare_digest(expected, current):
        app.logger.warning("Session fingerprint mismatch for user %s", session.get("user_id"))
        session.clear()
        if _wants_json_response():
            return jsonify({"ok": False, "msg": "Session expired. Please sign in again."}), 401
        return redirect(url_for("auth.login"))

    session.permanent = True
    return None


@app.before_request
def protect_csrf():
    if request.method in {"GET", "HEAD", "OPTIONS", "TRACE"}:
        _ensure_csrf_token()
        return None
    token = session.get("_csrf_token")
    candidate = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
    if not candidate and request.is_json:
        payload = request.get_json(silent=True) or {}
        candidate = payload.get("csrf_token")
    if not token or not candidate or not secrets.compare_digest(candidate, token):
        abort(400, description="CSRF validation failed.")
    return None


@app.before_request
def rate_limit_sensitive_endpoints():
    if request.endpoint == "auth.login" and request.method == "POST":
        return None
    limit = _API_RATE_LIMITS.get(request.endpoint)
    if not limit:
        return None

    key = f"{request.endpoint}:{session.get('user_id') or _client_ip()}"
    allowed, retry_after = rate_limiter.hit(
        key,
        limit,
        Config.API_RATE_LIMIT_WINDOW_SECONDS,
    )
    if allowed:
        return None

    message = "Too many requests. Please slow down and try again shortly."
    if _wants_json_response():
        return jsonify({"ok": False, "msg": message, "retry_after": retry_after}), 429
    return _error_response(429, message)


@app.after_request
def set_security_headers(response):
    response.headers.setdefault("Content-Security-Policy", _content_security_policy())
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.is_secure:
        response.headers.setdefault(
            "Strict-Transport-Security",
            f"max-age={Config.HSTS_MAX_AGE}; includeSubDomains",
        )
    return response


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))
    from database import close_db, get_db

    conn = get_db()
    cur = conn.cursor()
    role = session.get("role")
    loc_id = session.get("location_id")

    base = "FROM inquiries i WHERE 1=1"
    params = []
    if role == "teacher" and loc_id:
        base += " AND i.location_id=%s"
        params.append(loc_id)

    cur.execute(f"SELECT COUNT(*) AS c {base}", params)
    total = cur.fetchone()["c"]
    cur.execute(f"SELECT COUNT(*) AS c {base} AND i.status='Open'", params)
    open_c = cur.fetchone()["c"]
    cur.execute(f"SELECT COUNT(*) AS c {base} AND i.status='Converted'", params)
    converted = cur.fetchone()["c"]
    cur.execute(f"SELECT COUNT(*) AS c {base} AND i.status='Closed'", params)
    closed = cur.fetchone()["c"]

    cur.execute(f"SELECT COALESCE(SUM(fees_paid),0) AS rev {base} AND i.status='Converted'", params)
    revenue = cur.fetchone()["rev"]
    cur.execute(
        f"SELECT COALESCE(SUM(fees_total-fees_paid),0) AS pend {base} AND i.status='Converted'",
        params,
    )
    pending = cur.fetchone()["pend"]

    base2 = """
        FROM inquiries i
        LEFT JOIN locations l ON i.location_id=l.id
        LEFT JOIN courses c ON i.course_id=c.id
        WHERE 1=1
    """
    p2 = []
    if role == "teacher" and loc_id:
        base2 += " AND i.location_id=%s"
        p2.append(loc_id)
    cur.execute(
        f"SELECT i.*,l.name AS location_name,c.name AS course_name {base2} ORDER BY i.created_at DESC LIMIT 6",
        p2,
    )
    recent = cur.fetchall()

    cur.execute(f"SELECT COUNT(*) AS c {base} AND i.followup_date=CURRENT_DATE AND i.status='Open'", params)
    todays_fu = cur.fetchone()["c"]

    cur.execute(
        f"""
        SELECT TO_CHAR(inquiry_date,'YYYY-MM') AS month,
               TO_CHAR(inquiry_date,'Mon YY') AS month_label,
               COUNT(*) AS inquiries,
               SUM(CASE WHEN status='Converted' THEN 1 ELSE 0 END) AS admissions
        {base}
        AND inquiry_date >= NOW() - INTERVAL '6 months'
        GROUP BY TO_CHAR(inquiry_date,'YYYY-MM'), TO_CHAR(inquiry_date,'Mon YY')
        ORDER BY TO_CHAR(inquiry_date,'YYYY-MM')
        """,
        params,
    )
    trend = cur.fetchall()

    close_db(conn, commit=False)
    return render_template(
        "dashboard.html",
        total=total,
        open_c=open_c,
        converted=converted,
        closed=closed,
        revenue=revenue,
        pending=pending,
        recent=recent,
        todays_fu=todays_fu,
        trend=trend,
    )


@app.errorhandler(400)
def bad_request(err):
    return _error_response(400, getattr(err, "description", "Bad request."))


@app.errorhandler(403)
def forbidden(_err):
    return _error_response(403, "Access denied.")


@app.errorhandler(404)
def not_found(_err):
    return _error_response(404, "Page not found.")


@app.errorhandler(429)
def too_many_requests(_err):
    return _error_response(429, "Too many requests. Please try again later.")


@app.errorhandler(Exception)
def handle_unexpected_error(err):
    if isinstance(err, HTTPException):
        return err
    app.logger.exception("Unhandled application error")
    return _error_response(500, "Internal server error.")


if __name__ == "__main__":
    ssl_context = None
    if Config.SSL_CERT_FILE and Config.SSL_KEY_FILE:
        ssl_context = (Config.SSL_CERT_FILE, Config.SSL_KEY_FILE)
    socketio.run(
        app,
        debug=Config.DEBUG,
        host="127.0.0.1" if Config.DEBUG else "0.0.0.0",
        port=Config.PORT,
        ssl_context=ssl_context,
        allow_unsafe_werkzeug=True,
    )
