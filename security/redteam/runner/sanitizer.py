"""Shared sensitive-value detection and redaction for QA results."""

from __future__ import annotations

import re
import unicodedata
from bisect import bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

REDACTED = "[REDACTED]"
ACCOUNT_KEYS = frozenset(
    {
        "account_no",
        "account_number",
        "bank_account",
        "recipient_account_number",
    }
)
SENSITIVE_KEYS = frozenset(
    {
        *ACCOUNT_KEYS,
        "access_token",
        "api-key",
        "api_key",
        "authorization",
        "client-secret",
        "client_secret",
        "cookie",
        "id_token",
        "password",
        "refresh_token",
        "secret",
        "set-cookie",
        "token",
    }
)


def _canonical_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(char for char in normalized if char.isalnum())


_CANONICAL_ACCOUNT_KEYS = frozenset(_canonical_key(key) for key in ACCOUNT_KEYS)
_CANONICAL_SENSITIVE_KEYS = frozenset(_canonical_key(key) for key in SENSITIVE_KEYS)
_ASSIGNMENT_OPERATOR = re.compile(r"[:=]")
_ASSIGNMENT_KEY_BOUNDARY = frozenset("\r\n,;?&#{}[]")
_ASSIGNMENT_RECORD_PREFIX = frozenset({*_ASSIGNMENT_KEY_BOUNDARY, '"', "'"})
_ASSIGNMENT_VALUE_SEPARATOR = frozenset("\r\n,;?&#{}[]\"'")
_URL_VALUE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://")
_ACCOUNT_CANDIDATE = re.compile(r"(?<!\d)\d{2,16}(?:[ -]+\d{2,16})*(?!\d)")
_MFS_ACCOUNT_CANDIDATE = re.compile(r"(?i)(?<![A-Z0-9])MFS[0-9A-F]{12}(?![A-Z0-9])")
_ACCOUNT_LABEL = re.compile(
    r"(?i)(?:계좌(?:\s*번호)?|account\s*(?:number|no)?|bank\s*account)"
)
_BEARER_TOKEN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_AUTH_VALUE = re.compile(
    r"(?im)\b(authorization\s*[:=]\s*).*?"
    r"(?=\s+(?:token|api[_-]?key|secret|password|(?:set-)?cookie|authorization)"
    r"\s*[:=]|$)"
)
_COOKIE_VALUE = re.compile(
    r"(?i)\b((?:set-)?cookie\s*[:=]\s*)[^,\s;]+(?:\s*;\s*[^,\s;]+)*"
)


def _matching_key_suffix_start(
    value: str,
    sensitive_keys: set[str],
) -> int | None:
    sensitive_keys = {key for key in sensitive_keys if key}
    if not sensitive_keys:
        return None
    unquoted = value.strip().strip("\"'")
    leading = value.find(unquoted) if unquoted else 0
    canonical = []
    offsets = []
    for index, character in enumerate(unquoted):
        for normalized in unicodedata.normalize("NFKC", character).casefold():
            if normalized.isalnum():
                canonical.append(normalized)
                offsets.append(index)
    canonical_value = "".join(canonical)
    for sensitive_key in sorted(sensitive_keys, key=len, reverse=True):
        if not canonical_value.endswith(sensitive_key):
            continue
        canonical_start = len(canonical_value) - len(sensitive_key)
        original_start = offsets[canonical_start]
        if original_start == 0:
            return leading
        previous = unquoted[original_start - 1]
        if previous.isspace() or unicodedata.category(previous)[0] in "PS":
            return leading + original_start
    return None


def _normalized_scan_with_offsets(value: str) -> tuple[str, list[int]]:
    scan = []
    offsets = []
    for original_index, character in enumerate(value):
        normalized = unicodedata.normalize("NFKC", character)
        if unicodedata.category(character) == "Cf":
            normalized = " "
        for normalized_character in normalized:
            category = unicodedata.category(normalized_character)
            if normalized_character.isspace() or category.startswith("Z"):
                scan.append(" ")
            elif category.startswith("P"):
                scan.append("-")
            else:
                scan.append(normalized_character)
            offsets.append(original_index)
    return "".join(scan), offsets


def _key_scan_with_offsets(value: str) -> tuple[str, list[int]]:
    scan = []
    offsets = []
    for original_index, character in enumerate(value):
        normalized = unicodedata.normalize("NFKC", character)
        if unicodedata.category(character) == "Cf":
            normalized = " "
        for normalized_character in normalized:
            scan.append(normalized_character)
            offsets.append(original_index)
    return "".join(scan), offsets


def _valid_time(hour: int, minute: int, second: int = 0) -> bool:
    return 0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59


def _looks_like_datetime(groups: list[str]) -> bool:
    if len(groups) == 2 and len(groups[0]) == 8 and len(groups[1]) in {4, 6}:
        date_part, time_part = groups
        year = int(date_part[:4])
        month = int(date_part[4:6])
        day = int(date_part[6:8])
        second = int(time_part[4:6]) if len(time_part) == 6 else 0
        return (
            1900 <= year <= 2200
            and 1 <= month <= 12
            and 1 <= day <= 31
            and _valid_time(int(time_part[:2]), int(time_part[2:4]), second)
        )
    if len(groups) < 3 or len(groups[0]) != 4:
        return False
    year, month, day = map(int, groups[:3])
    if not (1900 <= year <= 2200 and 1 <= month <= 12 and 1 <= day <= 31):
        return False
    time_groups = groups[3:]
    if not time_groups:
        return True
    if len(time_groups) == 1 and len(time_groups[0]) in {4, 6}:
        compact = time_groups[0]
        second = int(compact[4:6]) if len(compact) == 6 else 0
        return _valid_time(int(compact[:2]), int(compact[2:4]), second)
    if len(time_groups) in {2, 3} and all(len(group) == 2 for group in time_groups):
        hour, minute = map(int, time_groups[:2])
        second = int(time_groups[2]) if len(time_groups) == 3 else 0
        return _valid_time(hour, minute, second)
    return False


def _is_account_candidate(text: str, match: re.Match[str]) -> bool:
    candidate = match.group()
    groups = re.findall(r"\d+", candidate)
    digit_count = sum(len(group) for group in groups)
    if not 9 <= digit_count <= 16:
        return False
    if _looks_like_datetime(groups):
        return False
    context = text[max(0, match.start() - 24) : min(len(text), match.end() + 24)]
    if _ACCOUNT_LABEL.search(context):
        return True
    return [len(group) for group in groups] == [3, 3, 6]


def _account_spans(value: str) -> list[tuple[int, int]]:
    scan, offsets = _normalized_scan_with_offsets(value)
    spans = []
    matches = [
        match
        for pattern in (_ACCOUNT_CANDIDATE, _MFS_ACCOUNT_CANDIDATE)
        for match in pattern.finditer(scan)
    ]
    for match in sorted(matches, key=lambda item: item.start()):
        if match.re is _ACCOUNT_CANDIDATE and not _is_account_candidate(scan, match):
            continue
        start = offsets[match.start()]
        end = offsets[match.end() - 1] + 1
        if not spans or start > spans[-1][1]:
            spans.append((start, end))
        else:
            spans[-1] = (spans[-1][0], max(spans[-1][1], end))
    return spans


def _account_match(value: str) -> bool:
    return bool(_account_spans(value))


def _redact_account_text(value: str) -> str:
    spans = _account_spans(value)
    for start, end in reversed(spans):
        value = value[:start] + REDACTED + value[end:]
    return value


def _scalar_sequence_account(value: Sequence[object]) -> bool:
    has_nested_value = any(
        isinstance(item, (Mapping, Sequence)) and not isinstance(item, str)
        for item in value
    )
    if not value or has_nested_value:
        return False
    scalar_text = " ".join(str(item) for item in value if isinstance(item, (str, int)))
    return _account_match(scalar_text)


def contains_account_identifier(value: object, account_context: bool = False) -> bool:
    if account_context and isinstance(value, int) and not isinstance(value, bool):
        return 9 <= len(str(abs(value))) <= 16
    if isinstance(value, str):
        if account_context and value not in ("", REDACTED):
            return True
        return _account_match(value.replace(REDACTED, ""))
    if isinstance(value, Mapping):
        for key, item in value.items():
            canonical_key = _canonical_key(key) if isinstance(key, str) else ""
            if contains_account_identifier(
                item,
                canonical_key in _CANONICAL_ACCOUNT_KEYS,
            ):
                return True
        return False
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return _scalar_sequence_account(value) or any(
            contains_account_identifier(item, account_context) for item in value
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


@dataclass(frozen=True)
class _AssignmentOperator:
    start: int
    end: int
    key_start: int
    value_boundary: int
    line_boundary: int | None
    sensitive: bool
    structured: bool


def _assignment_operators(
    scan: str,
    sensitive_keys: set[str],
) -> list[_AssignmentOperator]:
    operators = list(_ASSIGNMENT_OPERATOR.finditer(scan))
    result = []
    previous_operator_end = 0
    last_hard_boundary = 0
    last_line_boundary: int | None = None
    boundary_cursor = 0
    for operator in operators:
        while boundary_cursor < operator.start():
            if scan[boundary_cursor] in _ASSIGNMENT_KEY_BOUNDARY:
                last_hard_boundary = boundary_cursor + 1
            if scan[boundary_cursor] in "\r\n":
                last_line_boundary = boundary_cursor
            boundary_cursor += 1

        search_floor = max(previous_operator_end, last_hard_boundary)
        key_scope = scan[search_floor : operator.start()]
        sensitive_start = _matching_key_suffix_start(key_scope, sensitive_keys)
        key_start = operator.start()
        while key_start > search_floor and not scan[key_start - 1].isspace():
            key_start -= 1
        if sensitive_start is not None:
            key_start = search_floor + sensitive_start
        key = scan[key_start : operator.start()].strip("\"'")
        is_url_scheme = operator.group() == ":" and scan[operator.end() :].startswith(
            "//"
        )

        value_boundary = key_start
        while value_boundary > 0:
            marker_start = value_boundary - len(REDACTED)
            if marker_start >= 0 and scan.startswith(REDACTED, marker_start):
                break
            previous = scan[value_boundary - 1]
            if not (previous.isspace() or previous in _ASSIGNMENT_VALUE_SEPARATOR):
                break
            value_boundary -= 1

        has_record_boundary = key_start == 0 or (
            scan[key_start - 1].isspace()
            or scan[key_start - 1] in _ASSIGNMENT_RECORD_PREFIX
        )
        if (
            has_record_boundary
            and any(character.isalpha() for character in key)
            and not is_url_scheme
        ):
            result.append(
                _AssignmentOperator(
                    start=operator.start(),
                    end=operator.end(),
                    key_start=key_start,
                    value_boundary=value_boundary,
                    line_boundary=last_line_boundary,
                    sensitive=sensitive_start is not None,
                    structured=(
                        operator.group() == ":"
                        and key_start > 0
                        and scan[key_start - 1] in "\"'"
                    ),
                )
            )
        previous_operator_end = operator.end()
    return result


def _url_value_end(scan: str, value_start: int) -> int | None:
    if not _URL_VALUE.match(scan, value_start):
        return None
    end = value_start
    while end < len(scan) and not scan[end].isspace():
        end += 1
    return end


def _assignment_value_spans(
    value: str,
    sensitive_keys: set[str],
) -> list[tuple[int, int]]:
    scan, offsets = _key_scan_with_offsets(value)
    assignments = _assignment_operators(scan, sensitive_keys)
    assignment_starts = [assignment.start for assignment in assignments]
    spans = []
    for operator in assignments:
        if not operator.sensitive:
            continue
        value_start = operator.end
        while value_start < len(scan) and scan[value_start].isspace():
            value_start += 1
        if value_start >= len(scan):
            continue
        quote = scan[value_start] if scan[value_start] in "\"'" else None
        if quote is not None:
            closing = scan.find(quote, value_start + 1)
            value_end = closing + 1 if closing >= 0 else len(scan)
        else:
            url_end = _url_value_end(scan, value_start)
            if url_end is not None:
                value_end = url_end
            elif operator.structured:
                structural_ends = [
                    position
                    for separator in ",}"
                    if (position := scan.find(separator, value_start)) >= 0
                ]
                value_end = min(structural_ends, default=len(scan))
            else:
                next_index = bisect_right(assignment_starts, value_start)
                if next_index < len(assignments):
                    next_assignment = assignments[next_index]
                    value_end = next_assignment.value_boundary
                    if (
                        next_assignment.line_boundary is not None
                        and next_assignment.line_boundary > value_start
                    ):
                        value_end = min(value_end, next_assignment.line_boundary)
                else:
                    value_end = len(scan)
        while value_end > value_start and scan[value_end - 1].isspace():
            value_end -= 1
        if value_end <= value_start:
            continue
        captured = scan[value_start:value_end].strip()
        unquoted = captured
        if len(captured) >= 2 and captured[0] in "\"'" and captured[-1] == captured[0]:
            unquoted = captured[1:-1].strip()
        if unquoted == REDACTED:
            continue
        start = offsets[value_start]
        end = offsets[value_end - 1] + 1
        spans.append((start, end))
    merged = []
    for start, end in sorted(set(spans)):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _contains_inline_secret(value: str, sensitive_keys: set[str]) -> bool:
    return bool(_assignment_value_spans(value, sensitive_keys))


def contains_sensitive_data(value: object, fields: set[str]) -> bool:
    normalized_fields = {
        *(_canonical_key(field) for field in fields if _canonical_key(field)),
        *_CANONICAL_SENSITIVE_KEYS,
    }

    def contains(item: object, account_context: bool = False) -> bool:
        if isinstance(item, str):
            if account_context and item not in ("", REDACTED):
                return True
            clean = item.replace(REDACTED, "")
            if _account_match(clean) or _BEARER_TOKEN.search(clean):
                return True
            if _contains_inline_secret(item, normalized_fields):
                return True
            return any(
                REDACTED not in match.group()
                for pattern in (_AUTH_VALUE, _COOKIE_VALUE)
                for match in pattern.finditer(item)
            )
        if isinstance(item, Mapping):
            for key, nested in item.items():
                canonical_key = _canonical_key(key) if isinstance(key, str) else ""
                if canonical_key in normalized_fields and nested not in (
                    None,
                    "",
                    REDACTED,
                ):
                    return True
                if contains(nested, canonical_key in _CANONICAL_ACCOUNT_KEYS):
                    return True
            return False
        if isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            if _scalar_sequence_account(item):
                return True
            return any(contains(nested, account_context) for nested in item)
        if account_context and isinstance(item, int) and not isinstance(item, bool):
            return 9 <= len(str(abs(item))) <= 16
        return False

    return contains(value)


def _redact_inline_secrets(value: str, sensitive_keys: set[str]) -> str:
    for start, end in reversed(_assignment_value_spans(value, sensitive_keys)):
        value = value[:start] + REDACTED + value[end:]
    return value


def redact(value: object, fields: set[str]) -> object:
    normalized_fields = {
        *(_canonical_key(field) for field in fields if _canonical_key(field)),
        *_CANONICAL_SENSITIVE_KEYS,
    }

    def visit(item: object, account_context: bool = False) -> object:
        if isinstance(item, Mapping):
            result = {}
            for key, nested in item.items():
                canonical_key = _canonical_key(key) if isinstance(key, str) else ""
                if canonical_key in normalized_fields:
                    result[key] = REDACTED
                else:
                    result[key] = visit(
                        nested,
                        canonical_key in _CANONICAL_ACCOUNT_KEYS,
                    )
            return result
        if isinstance(item, list):
            if _scalar_sequence_account(item):
                return [REDACTED]
            return [visit(nested, account_context) for nested in item]
        if account_context and item not in (None, "", REDACTED):
            return REDACTED
        if isinstance(item, str):
            item = _redact_account_text(item)
            item = _BEARER_TOKEN.sub(f"Bearer {REDACTED}", item)
            item = _AUTH_VALUE.sub(rf"\1{REDACTED}", item)
            item = _COOKIE_VALUE.sub(rf"\1{REDACTED}", item)
            return _redact_inline_secrets(item, normalized_fields)
        return item

    return visit(value)
