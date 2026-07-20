"""Shared sensitive-value detection and redaction for QA results."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

REDACTED = "[REDACTED]"
SENSITIVE_KEYS = frozenset(
    {
        "access_token",
        "account_no",
        "account_number",
        "api-key",
        "api_key",
        "authorization",
        "bank_account",
        "client-secret",
        "client_secret",
        "cookie",
        "id_token",
        "password",
        "recipient_account_number",
        "refresh_token",
        "secret",
        "set-cookie",
        "token",
    }
)
_SENSITIVE_KEY_PATTERN = "|".join(
    re.escape(key) for key in sorted(SENSITIVE_KEYS, key=len, reverse=True)
)
_ACCOUNT_LIKE = re.compile(r"(?<!\d)\d{2,16}(?:[ .-]\d{2,16})*(?!\d)")
_BEARER_TOKEN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_AUTH_VALUE = re.compile(
    r"(?im)\b(authorization\s*[:=]\s*).*?"
    r"(?=\s+(?:token|api[_-]?key|secret|password|(?:set-)?cookie|authorization)"
    r"\s*[:=]|$)"
)
_COOKIE_VALUE = re.compile(
    r"(?i)\b((?:set-)?cookie\s*[:=]\s*)[^,\s;]+(?:\s*;\s*[^,\s;]+)*"
)
_SECRET_VALUE = re.compile(
    rf"(?i)\b((?:{_SENSITIVE_KEY_PATTERN})[\"']?\s*[:=]\s*)"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;&]+)"
)


def _account_match(value: str) -> bool:
    return any(
        9 <= sum(char.isdigit() for char in match.group()) <= 16
        for match in _ACCOUNT_LIKE.finditer(value)
    )


def _numeric_account(value: object) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and 10**8 <= value < 10**16
    )


def _scalar_sequence_account(value: Sequence[object]) -> bool:
    has_nested_value = any(
        isinstance(item, (Mapping, Sequence)) and not isinstance(item, str)
        for item in value
    )
    if not value or has_nested_value:
        return False
    scalar_text = " ".join(str(item) for item in value if isinstance(item, (str, int)))
    return _account_match(scalar_text)


def contains_account_identifier(value: object) -> bool:
    if _numeric_account(value):
        return True
    if isinstance(value, str):
        return _account_match(value.replace(REDACTED, ""))
    if isinstance(value, Mapping):
        for key, item in value.items():
            if (
                isinstance(key, str)
                and key.casefold() in SENSITIVE_KEYS
                and item not in (None, "", REDACTED)
            ):
                return True
            if contains_account_identifier(item):
                return True
        return False
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return _scalar_sequence_account(value) or any(
            contains_account_identifier(item) for item in value
        )
    return False


def contains_bearer_token(value: object) -> bool:
    if isinstance(value, str):
        return bool(_BEARER_TOKEN.search(value.replace(REDACTED, "")))
    if isinstance(value, Mapping):
        return any(contains_bearer_token(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(contains_bearer_token(item) for item in value)
    return False


def contains_sensitive_data(value: object, fields: set[str]) -> bool:
    return redact(value, fields) != value


def _redact_account_match(match: re.Match[str]) -> str:
    digit_count = sum(char.isdigit() for char in match.group())
    return REDACTED if 9 <= digit_count <= 16 else match.group()


def redact(value: object, fields: set[str]) -> object:
    normalized_fields = {field.casefold() for field in fields} | SENSITIVE_KEYS
    if isinstance(value, Mapping):
        return {
            key: REDACTED
            if isinstance(key, str) and key.casefold() in normalized_fields
            else redact(item, normalized_fields)
            for key, item in value.items()
        }
    if isinstance(value, list):
        if _scalar_sequence_account(value):
            return [REDACTED]
        return [redact(item, normalized_fields) for item in value]
    if _numeric_account(value):
        return REDACTED
    if isinstance(value, str):
        value = _ACCOUNT_LIKE.sub(_redact_account_match, value)
        value = _BEARER_TOKEN.sub(f"Bearer {REDACTED}", value)
        value = _AUTH_VALUE.sub(rf"\1{REDACTED}", value)
        value = _COOKIE_VALUE.sub(rf"\1{REDACTED}", value)
        return _SECRET_VALUE.sub(rf"\1{REDACTED}", value)
    return value
