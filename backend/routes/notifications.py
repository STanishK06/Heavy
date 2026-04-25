"""
routes/notifications.py - notification HTTP endpoints and Socket.IO handlers
"""
from __future__ import annotations

import secrets

from flask import Blueprint, current_app, jsonify, request, session
from flask_socketio import ConnectionRefusedError, SocketIO, emit, join_room

from config import Config
from database import close_db, get_db
from rate_limit import rate_limiter
from routes.auth import login_required
from security import build_session_fingerprint

notif_bp = Blueprint("notifications", __name__, url_prefix="/notifications")
socketio = SocketIO()

_VISIBLE_ROLES = ("teacher", "admin", "developer")


def _visibility_scope(role):
    return " AND (target_role IS NULL OR target_role=%s)", [role]


def _serialize_notification(row):
    item = dict(row)
    if item.get("created_at"):
        item["created_at"] = str(item["created_at"])
    return item


def _notification_snapshot(role):
    conn = get_db()
    cur = conn.cursor()
    try:
        scope_sql, params = _visibility_scope(role)
        cur.execute(f"SELECT COUNT(*) AS c FROM notifications WHERE is_read=FALSE{scope_sql};", params)
        count = cur.fetchone()["c"]
        cur.execute(
            f"SELECT * FROM notifications WHERE 1=1{scope_sql} ORDER BY created_at DESC LIMIT 30;",
            params,
        )
        notifications = [_serialize_notification(row) for row in cur.fetchall()]
        return {"type": "snapshot", "count": count, "notifications": notifications}
    finally:
        close_db(conn, commit=False)


def _role_room(role):
    return f"notifications:role:{role}"


def _is_local_request():
    host = (request.host or "").split(":", 1)[0]
    return host in {"127.0.0.1", "localhost"}


def _require_socket_auth(auth):
    if "user_id" not in session:
        raise ConnectionRefusedError("Authentication required.")
    expected_fingerprint = session.get("session_fingerprint")
    current_fingerprint = build_session_fingerprint(
        (request.access_route[0] if request.access_route else request.remote_addr or "unknown")[:64],
        request.user_agent.string or "",
    )
    if expected_fingerprint and current_fingerprint and not secrets.compare_digest(expected_fingerprint, current_fingerprint):
        raise ConnectionRefusedError("Session expired.")
    if Config.SOCKETIO_REQUIRE_CSRF_AUTH:
        session_token = session.get("_csrf_token")
        candidate = (auth or {}).get("csrfToken")
        if not session_token or not candidate or not secrets.compare_digest(candidate, session_token):
            raise ConnectionRefusedError("Socket authentication failed.")
    if not request.is_secure and not current_app.debug and not _is_local_request():
        raise ConnectionRefusedError("Secure socket transport required.")
    return session["user_id"], session.get("role")


def _broadcast_snapshot(target_role=None):
    roles = (target_role,) if target_role else _VISIBLE_ROLES
    for role in roles:
        socketio.emit(
            "notification_snapshot",
            _notification_snapshot(role),
            to=_role_room(role),
            namespace="/notifications",
        )


@notif_bp.route("/count")
@login_required
def count():
    snapshot = _notification_snapshot(session.get("role"))
    return jsonify({"count": snapshot["count"]})


@notif_bp.route("/list")
@login_required
def list_all():
    snapshot = _notification_snapshot(session.get("role"))
    return jsonify(snapshot["notifications"])


@notif_bp.route("/snapshot")
@login_required
def snapshot():
    return jsonify(_notification_snapshot(session.get("role")))


@notif_bp.route("/<int:nid>/read", methods=["POST"])
@login_required
def mark_read(nid):
    conn = get_db()
    cur = conn.cursor()
    scope_sql, params = _visibility_scope(session.get("role"))
    cur.execute(f"UPDATE notifications SET is_read=TRUE WHERE id=%s{scope_sql};", [nid] + params)
    close_db(conn)
    _broadcast_snapshot(session.get("role"))
    return jsonify({"ok": True})


@notif_bp.route("/read-all", methods=["POST"])
@login_required
def read_all():
    conn = get_db()
    cur = conn.cursor()
    scope_sql, params = _visibility_scope(session.get("role"))
    cur.execute(f"UPDATE notifications SET is_read=TRUE WHERE 1=1{scope_sql};", params)
    close_db(conn)
    _broadcast_snapshot(session.get("role"))
    return jsonify({"ok": True})


@socketio.on("connect", namespace="/notifications")
def notifications_connect(auth):
    user_id, role = _require_socket_auth(auth)
    join_room(_role_room(role))
    emit("notification_test", {"ok": True, "message": "Socket connected."})
    emit("notification_snapshot", _notification_snapshot(role))
    current_app.logger.info("Notification socket connected for user %s", user_id)


@socketio.on("disconnect", namespace="/notifications")
def notifications_disconnect(reason=None):
    current_app.logger.info("Notification socket disconnected: %s", reason)


@socketio.on("notification_refresh", namespace="/notifications")
def notification_refresh(_payload=None):
    role = session.get("role")
    allowed, retry_after = rate_limiter.hit(
        f"socket-refresh:{request.sid}",
        Config.WEBSOCKET_REFRESH_MAX_MESSAGES,
        Config.WEBSOCKET_REFRESH_WINDOW_SECONDS,
    )
    if not allowed:
        emit(
            "notification_error",
            {"ok": False, "msg": "Too many refresh requests.", "retry_after": retry_after},
        )
        return
    emit("notification_snapshot", _notification_snapshot(role))


@socketio.on_error("/notifications")
def notification_socket_error(exc):
    current_app.logger.exception("Notification socket error: %s", exc)
    emit("notification_error", {"ok": False, "msg": "Notification stream error."})


def create_notification(title, message, target_role=None):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO notifications (title,message,target_role)
            VALUES (%s,%s,%s);
            """,
            (title, message, target_role),
        )
        close_db(conn)
        _broadcast_snapshot(target_role)
    except Exception:
        current_app.logger.exception("Failed to create notification")
