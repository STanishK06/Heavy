"""
security.py - shared authentication security helpers
"""
from __future__ import annotations

import hashlib
from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

from config import Config

try:
    import bcrypt as bcrypt_lib
except ImportError:  # pragma: no cover - exercised by environment/runtime
    bcrypt_lib = None


_BCRYPT_PREFIXES = ("$2a$", "$2b$", "$2y$")


def bcrypt_available():
    return bcrypt_lib is not None


def hash_password(password):
    if bcrypt_lib is not None:
        hashed = bcrypt_lib.hashpw(
            password.encode("utf-8"),
            bcrypt_lib.gensalt(rounds=Config.BCRYPT_ROUNDS),
        )
        return hashed.decode("utf-8")
    if Config.DEBUG or Config.TESTING:
        return generate_password_hash(password, method="scrypt")
    raise RuntimeError("bcrypt must be installed to hash passwords in production.")


def verify_password(stored_hash, candidate):
    if not stored_hash:
        return False
    if stored_hash.startswith(_BCRYPT_PREFIXES):
        if bcrypt_lib is None:
            raise RuntimeError("bcrypt must be installed to verify bcrypt password hashes.")
        return bcrypt_lib.checkpw(candidate.encode("utf-8"), stored_hash.encode("utf-8"))
    return check_password_hash(stored_hash, candidate)


def needs_password_rehash(stored_hash):
    return bcrypt_lib is not None and not str(stored_hash or "").startswith(_BCRYPT_PREFIXES)


def is_lock_active(locked_until, now=None):
    if not locked_until:
        return False
    now = now or datetime.now()
    return locked_until > now


def build_session_fingerprint(ip_address, user_agent):
    parts = []
    if Config.SESSION_BIND_IP:
        parts.append((ip_address or "").strip()[:64])
    if Config.SESSION_BIND_USER_AGENT:
        parts.append((user_agent or "").strip()[:255])
    if not parts:
        return ""
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
