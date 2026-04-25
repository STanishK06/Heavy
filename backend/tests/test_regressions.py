import os
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path


os.environ["SKIP_INIT_DB"] = "1"
os.environ["DEBUG"] = "True"
os.environ["SECRET_KEY"] = "test-secret"

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import app as app_module  # noqa: E402
import rate_limit as rate_limit_module  # noqa: E402
import routes.auth as auth_module  # noqa: E402
import routes.courses as courses_module  # noqa: E402
import routes.inquiries as inquiries_module  # noqa: E402
import routes.locations as locations_module  # noqa: E402
import routes.notifications as notifications_module  # noqa: E402
import routes.offers as offers_module  # noqa: E402
import routes.users as users_module  # noqa: E402
import routes.whatsapp as whatsapp_module  # noqa: E402
from security import build_session_fingerprint  # noqa: E402


class StubCursor:
    def __init__(self, fetchone_values=None, fetchall_values=None):
        self.fetchone_values = list(fetchone_values or [])
        self.fetchall_values = list(fetchall_values or [])
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        if self.fetchone_values:
            return self.fetchone_values.pop(0)
        return None

    def fetchall(self):
        if self.fetchall_values:
            return self.fetchall_values.pop(0)
        return []


class StubConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def commit(self):
        pass

    def close(self):
        pass


class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.app = app_module.app
        self.app.config["TESTING"] = True
        self.csrf_token = "test-csrf-token"
        auth_module._reset_login_security_state()
        rate_limit_module.rate_limiter.reset()

    def add_csrf(self, sess):
        sess["_csrf_token"] = self.csrf_token

    def login_session(self, sess, role="developer", user_id=1, location_id=1):
        sess["user_id"] = user_id
        sess["username"] = f"{role}1"
        sess["role"] = role
        sess["location_id"] = location_id
        sess["login_ip"] = "127.0.0.1"
        sess["login_ua"] = "Werkzeug/Test"
        sess["session_fingerprint"] = build_session_fingerprint("127.0.0.1", "Werkzeug/Test")
        self.add_csrf(sess)

    def test_login_page_is_server_rendered(self):
        with self.app.test_client() as client:
            response = client.get(
                "/login",
                environ_overrides={"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "Werkzeug/Test"},
            )
            body = response.get_data(as_text=True)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("{%", body)
            self.assertNotIn("{{", body)
            self.assertIn("HeavyLift", body)

    def test_dashboard_page_does_not_leak_jinja_blocks(self):
        cursor = StubCursor(
            fetchone_values=[
                {"c": 10},
                {"c": 4},
                {"c": 3},
                {"c": 3},
                {"rev": 12500},
                {"pend": 2300},
                {"c": 2},
            ],
            fetchall_values=[
                [
                    {
                        "id": 1,
                        "name": "Aman",
                        "location_name": "Main Branch",
                        "course_name": "Powerlifting",
                    }
                ],
                [
                    {"month": "Jan", "inquiries": 5, "admissions": 2},
                    {"month": "Feb", "inquiries": 5, "admissions": 1},
                ],
            ],
        )
        app_module.get_db = lambda: StubConn(cursor)
        app_module.close_db = lambda conn, commit=True: None

        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                self.login_session(sess, role="developer", user_id=1, location_id=1)

            response = client.get(
                "/dashboard",
                environ_overrides={"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "Werkzeug/Test"},
            )
            body = response.get_data(as_text=True)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("{% block", body)
            self.assertNotIn("{{", body)
            self.assertIn("Dashboard", body)
            self.assertIn("HeavyLift", body)

    def test_teacher_cannot_change_other_users_password(self):
        cursor = StubCursor()
        auth_module.get_db = lambda: StubConn(cursor)
        auth_module.close_db = lambda conn, commit=True: None

        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                self.login_session(sess, role="teacher", user_id=99, location_id=1)

            response = client.post(
                "/users/1/change-password",
                json={"new_password": "secret123"},
                headers={"X-CSRF-Token": self.csrf_token},
                environ_overrides={"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "Werkzeug/Test"},
            )
            self.assertEqual(response.status_code, 403)
            self.assertFalse(cursor.executed)

    def test_offers_calculate_rejects_missing_json_payload(self):
        cursor = StubCursor()
        offers_module.get_db = lambda: StubConn(cursor)
        offers_module.close_db = lambda conn, commit=True: None

        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                self.login_session(sess)

            response = client.post(
                "/offers/api/calculate",
                data="course_id=1",
                content_type="application/x-www-form-urlencoded",
                headers={"X-CSRF-Token": self.csrf_token},
                environ_overrides={"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "Werkzeug/Test"},
            )
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.get_json()["msg"], "JSON body required")

    def test_teacher_cannot_access_whatsapp_templates_api(self):
        cursor = StubCursor()
        whatsapp_module.get_db = lambda: StubConn(cursor)
        whatsapp_module.close_db = lambda conn, commit=True: None

        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                self.login_session(sess, role="teacher", location_id=5)

            response = client.get(
                "/whatsapp/api/templates",
                environ_overrides={"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "Werkzeug/Test"},
            )
            self.assertEqual(response.status_code, 403)
            self.assertFalse(cursor.executed)

    def test_whatsapp_index_handles_database_failure_gracefully(self):
        def boom():
            raise RuntimeError("db unavailable")

        whatsapp_module.get_db = boom

        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                self.login_session(sess, role="admin")

            response = client.get(
                "/whatsapp/",
                environ_overrides={"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "Werkzeug/Test"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn("Unable to load WhatsApp templates right now.", response.get_data(as_text=True))

    def test_teacher_cannot_access_offers_index(self):
        cursor = StubCursor()
        offers_module.get_db = lambda: StubConn(cursor)
        offers_module.close_db = lambda conn, commit=True: None

        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                self.login_session(sess, role="teacher", location_id=5)

            response = client.get(
                "/offers/",
                follow_redirects=False,
                environ_overrides={"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "Werkzeug/Test"},
            )
            self.assertEqual(response.status_code, 302)
            self.assertFalse(cursor.executed)

    def test_login_rate_limit_returns_429_after_repeated_failures(self):
        cursor = StubCursor(fetchone_values=[None, None, None, None, None])
        auth_module.get_db = lambda: StubConn(cursor)
        auth_module.close_db = lambda conn, commit=True: None

        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                self.add_csrf(sess)

            for _ in range(5):
                response = client.post(
                    "/login",
                    data={"username": "unknown", "password": "wrong"},
                    headers={"X-CSRF-Token": self.csrf_token},
                    environ_overrides={"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "Werkzeug/Test"},
                )
                self.assertEqual(response.status_code, 200)

            response = client.post(
                "/login",
                data={"username": "unknown", "password": "wrong"},
                headers={"X-CSRF-Token": self.csrf_token},
                environ_overrides={"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "Werkzeug/Test"},
            )
            self.assertEqual(response.status_code, 429)

    def test_locked_user_cannot_log_in(self):
        cursor = StubCursor(
            fetchone_values=[
                {
                    "id": 1,
                    "username": "locked",
                    "password_hash": "not-used",
                    "role": "admin",
                    "location_id": 1,
                    "failed_login_attempts": 5,
                    "locked_until": datetime.now() + timedelta(minutes=5),
                }
            ]
        )
        auth_module.get_db = lambda: StubConn(cursor)
        auth_module.close_db = lambda conn, commit=True: None

        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                self.add_csrf(sess)

            response = client.post(
                "/login",
                data={"username": "locked", "password": "wrong"},
                headers={"X-CSRF-Token": self.csrf_token},
                environ_overrides={"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "Werkzeug/Test"},
            )
            self.assertEqual(response.status_code, 429)

    def test_login_honeypot_blocks_submission(self):
        cursor = StubCursor()
        auth_module.get_db = lambda: StubConn(cursor)
        auth_module.close_db = lambda conn, commit=True: None

        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                self.add_csrf(sess)

            response = client.post(
                "/login",
                data={"username": "user", "password": "wrong", "website": "spam"},
                headers={"X-CSRF-Token": self.csrf_token},
                environ_overrides={"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "Werkzeug/Test"},
            )
            self.assertEqual(response.status_code, 400)
            self.assertFalse(cursor.executed)

    def test_secure_responses_include_csp_and_hsts(self):
        with self.app.test_client() as client:
            response = client.get("/login", base_url="https://localhost")
            self.assertEqual(response.status_code, 200)
            self.assertIn("upgrade-insecure-requests", response.headers["Content-Security-Policy"])
            self.assertIn("max-age=", response.headers["Strict-Transport-Security"])

    def test_logout_redirect_disables_caching(self):
        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                self.login_session(sess, role="developer")

            response = client.post(
                "/logout",
                headers={"X-CSRF-Token": self.csrf_token},
                follow_redirects=False,
                environ_overrides={"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "Werkzeug/Test"},
            )
            self.assertEqual(response.status_code, 302)
            self.assertIn("no-store", response.headers["Cache-Control"])

    def test_user_edit_updates_current_session_identity(self):
        cursor = StubCursor(
            fetchone_values=[{"id": 1, "username": "dev1", "email": "old@example.com", "role": "developer", "location_id": 1}],
            fetchall_values=[[{"id": 1, "name": "HQ"}]],
        )

        def make_conn():
            return StubConn(cursor)

        users_module.get_db = make_conn
        users_module.close_db = lambda conn, commit=True: None

        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                self.login_session(sess, role="developer", user_id=1, location_id=1)

            response = client.post(
                "/users/1/edit",
                data={"username": "dev_renamed", "email": "new@example.com", "location_id": ""},
                headers={"X-CSRF-Token": self.csrf_token},
                follow_redirects=False,
                environ_overrides={"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "Werkzeug/Test"},
            )
            self.assertEqual(response.status_code, 302)
            with client.session_transaction() as sess:
                self.assertEqual(sess["username"], "dev_renamed")
                self.assertIsNone(sess["location_id"])

    def test_inquiry_add_keeps_posted_values_when_validation_fails(self):
        cursor = StubCursor(fetchall_values=[[], [], []])
        inquiries_module.get_db = lambda: StubConn(cursor)
        inquiries_module.close_db = lambda conn, commit=True: None

        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                self.login_session(sess, role="developer")

            response = client.post(
                "/inquiries/add",
                data={
                    "name": "Alice",
                    "mobile": "9876543210",
                    "fees_paid": "1000",
                    "inquiry_date": "2026-04-26",
                },
                headers={"X-CSRF-Token": self.csrf_token},
                environ_overrides={"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "Werkzeug/Test"},
            )
            body = response.get_data(as_text=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn('value="Alice"', body)
            self.assertIn("Fees paid cannot be greater than total fees.", body)

    def test_reference_mobile_is_not_forced_to_be_ten_digits(self):
        cleaned = inquiries_module._validate_inquiry_form(
            {
                "name": "Alice",
                "mobile": "9876543210",
                "inquiry_date": "2026-04-26",
                "fees_paid": "0",
                "ref1_mobile": "12345",
            },
            0,
        )
        self.assertEqual(cleaned["ref1_mobile"], "12345")

    def test_offer_add_keeps_posted_values_when_validation_fails(self):
        cursor = StubCursor(fetchall_values=[[]])
        offers_module.get_db = lambda: StubConn(cursor)
        offers_module.close_db = lambda conn, commit=True: None

        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                self.login_session(sess, role="developer")

            response = client.post(
                "/offers/add",
                data={
                    "name": "Summer Offer",
                    "discount_type": "flat",
                    "discount_value": "500",
                    "valid_from": "2026-05-10",
                    "valid_to": "2026-05-01",
                    "is_active": "true",
                },
                headers={"X-CSRF-Token": self.csrf_token},
                environ_overrides={"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "Werkzeug/Test"},
            )
            body = response.get_data(as_text=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn('value="Summer Offer"', body)
            self.assertIn("Valid to date cannot be earlier than valid from date.", body)

    def test_teacher_cannot_access_other_locations_whatsapp_send(self):
        cursor = StubCursor(fetchone_values=[None])
        inquiries_module.get_db = lambda: StubConn(cursor)
        inquiries_module.close_db = lambda conn, commit=True: None

        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                self.login_session(sess, role="teacher", location_id=5)

            response = client.post(
                "/inquiries/7/whatsapp-send",
                json={"message": "hi"},
                headers={"X-CSRF-Token": self.csrf_token},
                environ_overrides={"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "Werkzeug/Test"},
            )
            self.assertEqual(response.status_code, 404)
            self.assertFalse(response.get_json()["ok"])

    def test_notifications_are_scoped_to_current_role(self):
        cursor = StubCursor(
            fetchone_values=[{"c": 2}, {"c": 2}],
            fetchall_values=[[{"id": 1, "is_read": False, "created_at": None}]],
        )
        notifications_module.get_db = lambda: StubConn(cursor)
        notifications_module.close_db = lambda conn, commit=True: None

        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                self.login_session(sess, role="admin")

            count_response = client.get(
                "/notifications/count",
                environ_overrides={"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "Werkzeug/Test"},
            )
            list_response = client.get(
                "/notifications/list",
                environ_overrides={"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "Werkzeug/Test"},
            )

            self.assertEqual(count_response.status_code, 200)
            self.assertEqual(list_response.status_code, 200)
            self.assertIn("target_role IS NULL OR target_role=%s", cursor.executed[0][0])
            self.assertEqual(cursor.executed[0][1], ["admin"])

    def test_socketio_polling_handshake_is_mounted(self):
        with self.app.test_client() as client:
            response = client.get("/socket.io/?EIO=4&transport=polling")
            self.assertEqual(response.status_code, 200)
            self.assertIn('"upgrades":["websocket"]', response.get_data(as_text=True))

    def test_socketio_requires_authenticated_session(self):
        socket_client = notifications_module.socketio.test_client(
            self.app,
            namespace="/notifications",
            auth={"csrfToken": self.csrf_token},
        )
        self.assertFalse(socket_client.is_connected("/notifications"))

    def test_socketio_connect_emits_test_message_and_snapshot(self):
        cursor = StubCursor(
            fetchone_values=[{"c": 1}],
            fetchall_values=[[{"id": 9, "is_read": False, "created_at": None, "title": "Hi", "message": "There"}]],
        )
        notifications_module.get_db = lambda: StubConn(cursor)
        notifications_module.close_db = lambda conn, commit=True: None

        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                self.login_session(sess, role="admin")
                sess["session_fingerprint"] = ""

            socket_client = notifications_module.socketio.test_client(
                self.app,
                flask_test_client=client,
                namespace="/notifications",
                auth={"csrfToken": self.csrf_token},
            )
            self.assertTrue(socket_client.is_connected("/notifications"))
            received = socket_client.get_received("/notifications")
            names = [item["name"] for item in received]
            self.assertIn("notification_test", names)
            self.assertIn("notification_snapshot", names)
            socket_client.disconnect(namespace="/notifications")

    def test_socket_refresh_rate_limit_trips_after_threshold(self):
        cursor = StubCursor(
            fetchone_values=[{"c": 1}] * (notifications_module.Config.WEBSOCKET_REFRESH_MAX_MESSAGES + 1),
            fetchall_values=[[{"id": 1, "is_read": False, "created_at": None}]]
            * (notifications_module.Config.WEBSOCKET_REFRESH_MAX_MESSAGES + 1),
        )
        notifications_module.get_db = lambda: StubConn(cursor)
        notifications_module.close_db = lambda conn, commit=True: None

        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                self.login_session(sess, role="admin")
                sess["session_fingerprint"] = ""

            socket_client = notifications_module.socketio.test_client(
                self.app,
                flask_test_client=client,
                namespace="/notifications",
                auth={"csrfToken": self.csrf_token},
            )
            for _ in range(notifications_module.Config.WEBSOCKET_REFRESH_MAX_MESSAGES):
                socket_client.emit("notification_refresh", {"source": "test"}, namespace="/notifications")
            socket_client.emit("notification_refresh", {"source": "test"}, namespace="/notifications")
            events = socket_client.get_received("/notifications")
            self.assertTrue(any(event["name"] == "notification_error" for event in events))
            socket_client.disconnect(namespace="/notifications")

    def test_api_rate_limit_returns_429(self):
        cursor = StubCursor(fetchall_values=[[{"id": 1, "name": "Template"}]] * 61)
        whatsapp_module.get_db = lambda: StubConn(cursor)
        whatsapp_module.close_db = lambda conn, commit=True: None

        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                self.login_session(sess, role="admin")

            for _ in range(app_module.Config.API_RATE_LIMIT_MAX_REQUESTS):
                response = client.get(
                    "/whatsapp/api/templates",
                    environ_overrides={"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "Werkzeug/Test"},
                )
                self.assertEqual(response.status_code, 200)

            response = client.get(
                "/whatsapp/api/templates",
                environ_overrides={"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "Werkzeug/Test"},
            )
            self.assertEqual(response.status_code, 429)
            self.assertFalse(response.get_json()["ok"])

    def test_session_fingerprint_mismatch_invalidates_session(self):
        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                self.login_session(sess)

            response = client.get(
                "/dashboard",
                follow_redirects=False,
                environ_overrides={"REMOTE_ADDR": "10.0.0.1", "HTTP_USER_AGENT": "DifferentAgent"},
            )
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.headers["Location"].endswith("/login"))

    def test_teacher_locations_index_only_queries_assigned_location(self):
        cursor = StubCursor(fetchall_values=[[{"id": 5, "name": "Assigned"}]])
        locations_module.get_db = lambda: StubConn(cursor)
        locations_module.close_db = lambda conn, commit=True: None

        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                self.login_session(sess, role="teacher", location_id=5)

            response = client.get(
                "/locations/",
                environ_overrides={"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "Werkzeug/Test"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn("AND id=%s", cursor.executed[0][0])
            self.assertEqual(cursor.executed[0][1], [5])

    def test_teacher_cannot_open_other_location_analytics(self):
        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                self.login_session(sess, role="teacher", location_id=5)

            response = client.get(
                "/locations/9/analytics",
                follow_redirects=False,
                environ_overrides={"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "Werkzeug/Test"},
            )
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.headers["Location"].endswith("/locations/"))

    def test_teacher_course_analytics_is_scoped_to_assigned_location(self):
        cursor = StubCursor(fetchone_values=[None])
        courses_module.get_db = lambda: StubConn(cursor)
        courses_module.close_db = lambda conn, commit=True: None

        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                self.login_session(sess, role="teacher", location_id=5)

            response = client.get(
                "/courses/9/analytics",
                follow_redirects=False,
                environ_overrides={"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "Werkzeug/Test"},
            )
            self.assertEqual(response.status_code, 302)
            self.assertIn("AND c.location_id=%s", cursor.executed[0][0])
            self.assertEqual(cursor.executed[0][1], [9, 5])

    def test_courses_reorder_rejects_duplicate_ids(self):
        cursor = StubCursor()
        courses_module.get_db = lambda: StubConn(cursor)
        courses_module.close_db = lambda conn, commit=True: None

        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                self.login_session(sess)

            response = client.post(
                "/courses/reorder",
                json={"ids": [2, 2]},
                headers={"X-CSRF-Token": self.csrf_token},
                environ_overrides={"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "Werkzeug/Test"},
            )
            self.assertEqual(response.status_code, 400)
            self.assertFalse(cursor.executed)


if __name__ == "__main__":
    unittest.main()
