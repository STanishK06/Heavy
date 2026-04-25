"""
validation.py - shared input validation helpers
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import re


CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,50}$")
EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")


def clean_text(value, field_name, *, required=False, max_length=255, multiline=False):
    text = "" if value is None else str(value).strip()
    if not multiline:
        text = re.sub(r"\s+", " ", text)
    if required and not text:
        raise ValueError(f"{field_name} is required.")
    if text and CONTROL_CHAR_RE.search(text):
        raise ValueError(f"{field_name} contains invalid characters.")
    if max_length and len(text) > max_length:
        raise ValueError(f"{field_name} must be {max_length} characters or fewer.")
    return text


def clean_optional_text(value, field_name, *, max_length=255, multiline=False):
    text = clean_text(value, field_name, max_length=max_length, multiline=multiline)
    return text or None


def clean_username(value):
    username = clean_text(value, "Username", required=True, max_length=50)
    if not USERNAME_RE.fullmatch(username):
        raise ValueError("Username must be 3-50 characters and use only letters, numbers, ., _, or -.")
    return username


def clean_email(value):
    email = clean_text(value, "Email", required=True, max_length=120).lower()
    if not EMAIL_RE.fullmatch(email):
        raise ValueError("Email must be valid.")
    return email


def clean_choice(value, field_name, allowed, *, required=True):
    choice = clean_text(value, field_name, required=required, max_length=40)
    if not choice:
        return None
    if choice not in allowed:
        raise ValueError(f"{field_name} is invalid.")
    return choice


def parse_optional_int(value, field_name):
    raw = clean_optional_text(value, field_name, max_length=20)
    if raw is None:
        return None
    try:
        parsed = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a valid number.") from exc
    if parsed <= 0:
        raise ValueError(f"{field_name} must be greater than zero.")
    return parsed


def parse_decimal(value, field_name, *, min_value=Decimal("0"), max_value=None):
    raw = str(value or "").replace(",", "").strip()
    if not raw:
        raw = "0"
    try:
        parsed = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be a valid number.") from exc
    if parsed < min_value:
        raise ValueError(f"{field_name} cannot be negative.")
    if max_value is not None and parsed > max_value:
        raise ValueError(f"{field_name} is too large.")
    return parsed


def parse_optional_date(value, field_name):
    raw = clean_optional_text(value, field_name, max_length=20)
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid date.") from exc


def validate_ordered_ids(ids, field_name="ids"):
    if not isinstance(ids, list):
        raise ValueError(f"{field_name} must be a list.")
    cleaned = []
    seen = set()
    for raw in ids:
        try:
            parsed = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must contain only numeric IDs.") from exc
        if parsed <= 0:
            raise ValueError(f"{field_name} must contain only positive IDs.")
        if parsed in seen:
            raise ValueError(f"{field_name} cannot contain duplicate IDs.")
        seen.add(parsed)
        cleaned.append(parsed)
    return cleaned
