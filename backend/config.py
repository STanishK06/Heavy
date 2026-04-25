"""
config.py — HeavyLift CRM Configuration
Load from .env file. Never commit real credentials.
"""
import importlib.util
import os
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

def _as_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")

class Config:
    DEBUG        = _as_bool(os.getenv("DEBUG"), default=False)
    TESTING      = _as_bool(os.getenv("TESTING"), default=False)
    SECRET_KEY   = os.getenv("SECRET_KEY") or ("dev-secret-key-change-me" if DEBUG else None)
    DB_HOST      = os.getenv("DB_HOST", "localhost")
    DB_PORT      = os.getenv("DB_PORT", "5432")
    DB_NAME      = os.getenv("DB_NAME", "inquiry_db")
    DB_USER      = os.getenv("DB_USER", "postgres")
    DB_PASS      = os.getenv("DB_PASS", "")
    WA_API_URL   = os.getenv("WA_API_URL", "")
    WA_API_TOKEN = os.getenv("WA_API_TOKEN", "")
    WA_PHONE_ID  = os.getenv("WA_PHONE_ID", "")
    INIT_DB_ON_START       = _as_bool(os.getenv("INIT_DB_ON_START"), default=DEBUG)
    BOOTSTRAP_USERNAME     = os.getenv("BOOTSTRAP_USERNAME", "").strip()
    BOOTSTRAP_EMAIL        = os.getenv("BOOTSTRAP_EMAIL", "").strip()
    BOOTSTRAP_PASSWORD     = os.getenv("BOOTSTRAP_PASSWORD", "").strip()
    BOOTSTRAP_ROLE         = os.getenv("BOOTSTRAP_ROLE", "developer").strip().lower() or "developer"
    TRUST_PROXY_HEADERS    = _as_bool(os.getenv("TRUST_PROXY_HEADERS"), default=not DEBUG)
    HTTPS_REDIRECT         = _as_bool(os.getenv("HTTPS_REDIRECT"), default=not DEBUG)
    SESSION_COOKIE_SECURE  = _as_bool(os.getenv("SESSION_COOKIE_SECURE"), default=not DEBUG)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_REFRESH_EACH_REQUEST = True
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.getenv("SESSION_LIFETIME_HOURS", "12")))
    SESSION_BIND_IP = _as_bool(os.getenv("SESSION_BIND_IP"), default=not DEBUG)
    SESSION_BIND_USER_AGENT = _as_bool(os.getenv("SESSION_BIND_USER_AGENT"), default=True)
    PREFERRED_URL_SCHEME   = "https"
    HSTS_MAX_AGE           = int(os.getenv("HSTS_MAX_AGE", "31536000"))
    SOCKETIO_PING_INTERVAL = int(os.getenv("SOCKETIO_PING_INTERVAL", "25"))
    SOCKETIO_PING_TIMEOUT = int(os.getenv("SOCKETIO_PING_TIMEOUT", "20"))
    SOCKETIO_REQUIRE_CSRF_AUTH = _as_bool(os.getenv("SOCKETIO_REQUIRE_CSRF_AUTH"), default=True)
    LOGIN_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "60"))
    LOGIN_RATE_LIMIT_MAX_ATTEMPTS = int(os.getenv("LOGIN_RATE_LIMIT_MAX_ATTEMPTS", "5"))
    LOGIN_LOCKOUT_THRESHOLD = int(os.getenv("LOGIN_LOCKOUT_THRESHOLD", "5"))
    LOGIN_LOCKOUT_MINUTES = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "15"))
    API_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("API_RATE_LIMIT_WINDOW_SECONDS", "60"))
    API_RATE_LIMIT_MAX_REQUESTS = int(os.getenv("API_RATE_LIMIT_MAX_REQUESTS", "60"))
    MESSAGE_SEND_RATE_LIMIT_MAX_REQUESTS = int(os.getenv("MESSAGE_SEND_RATE_LIMIT_MAX_REQUESTS", "10"))
    BCRYPT_ROUNDS         = int(os.getenv("BCRYPT_ROUNDS", "12"))
    WEBSOCKET_REFRESH_WINDOW_SECONDS = int(os.getenv("WEBSOCKET_REFRESH_WINDOW_SECONDS", "10"))
    WEBSOCKET_REFRESH_MAX_MESSAGES = int(os.getenv("WEBSOCKET_REFRESH_MAX_MESSAGES", "5"))
    WEBSOCKET_MAX_INVALID_MESSAGES = int(os.getenv("WEBSOCKET_MAX_INVALID_MESSAGES", "3"))
    SSL_CERT_FILE          = os.getenv("SSL_CERT_FILE", "").strip() or None
    SSL_KEY_FILE           = os.getenv("SSL_KEY_FILE", "").strip() or None
    # For production deployment
    PORT         = int(os.getenv("PORT", 5000))

    @classmethod
    def validate_runtime(cls):
        if not cls.SECRET_KEY:
            raise RuntimeError("SECRET_KEY must be set when DEBUG is disabled.")
        if bool(cls.SSL_CERT_FILE) != bool(cls.SSL_KEY_FILE):
            raise RuntimeError("SSL_CERT_FILE and SSL_KEY_FILE must be provided together.")
        if not cls.DEBUG:
            if not cls.HTTPS_REDIRECT:
                raise RuntimeError("HTTPS_REDIRECT must stay enabled in production.")
            if not cls.SESSION_COOKIE_SECURE:
                raise RuntimeError("SESSION_COOKIE_SECURE must stay enabled in production.")
            if not (cls.TRUST_PROXY_HEADERS or (cls.SSL_CERT_FILE and cls.SSL_KEY_FILE)):
                raise RuntimeError(
                    "Production must run behind a trusted HTTPS proxy or provide local SSL cert files."
                )
            if importlib.util.find_spec("bcrypt") is None:
                raise RuntimeError("bcrypt must be installed in production.")
