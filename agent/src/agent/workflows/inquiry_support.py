"""거래내역과 기간 합계 Workflow가 공유하는 비금융 해석 유틸리티."""

from __future__ import annotations

import calendar
import re
from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_ACCOUNT_HINT = re.compile(
    r"([가-힣A-Za-z0-9]+)\s*(은행|통장|계좌)"
)
_EXPLICIT_DATES = re.compile(
    r"(?P<start>\d{4}-\d{2}-\d{2}).*?(?P<end>\d{4}-\d{2}-\d{2})"
)
_PERIOD_MARKERS = (
    "이번 달",
    "이번달",
    "지난 달",
    "지난달",
    "이번 주",
    "이번주",
    "지난 주",
    "지난주",
    "최근 한 달",
    "최근 한달",
    "최근 1개월",
    "작년",
    "올해",
    "분기",
)
_ALL_ACCOUNT_MARKERS = ("전체 계좌", "모든 계좌", "전 계좌")


def extract_account_hint(message: str) -> str | None:
    """은행명·계좌 별칭·계좌 유형으로 사용할 짧은 힌트를 추출한다."""

    match = _ACCOUNT_HINT.search(message)
    if match is None:
        return None
    hint = match.group(0).strip()
    if hint.replace(" ", "") in {"내계좌", "전체계좌", "모든계좌", "전계좌"}:
        return None
    return hint


def requests_all_accounts(message: str) -> bool:
    return any(marker in message for marker in _ALL_ACCOUNT_MARKERS)


def reference_date(
    data: Mapping[str, Any],
    *,
    fallback: datetime,
) -> date:
    """Execution Context의 요청시각과 Timezone을 사용자 기준 날짜로 바꾼다."""

    raw = data.get("requested_at")
    requested_at: datetime
    if isinstance(raw, datetime):
        requested_at = raw
    elif isinstance(raw, str):
        try:
            requested_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            requested_at = fallback
    else:
        requested_at = fallback

    if requested_at.tzinfo is None:
        requested_at = requested_at.replace(tzinfo=timezone.utc)

    timezone_name = data.get("timezone")
    try:
        user_timezone = ZoneInfo(
            timezone_name if isinstance(timezone_name, str) else "Asia/Seoul"
        )
    except ZoneInfoNotFoundError:
        user_timezone = ZoneInfo("Asia/Seoul")
    return requested_at.astimezone(user_timezone).date()


def extract_period_range(
    message: str,
    *,
    requested_date: date,
) -> tuple[str | None, str | None]:
    """안전하게 해석할 수 있는 기간 표현만 ISO 날짜로 변환한다."""

    explicit = _EXPLICIT_DATES.search(message)
    if explicit is not None:
        try:
            start = date.fromisoformat(explicit.group("start"))
            end = date.fromisoformat(explicit.group("end"))
        except ValueError:
            return None, None
        if end < start:
            return None, None
        return start.isoformat(), end.isoformat()

    compact = message.replace(" ", "")
    if "이번달" in compact:
        return requested_date.replace(day=1).isoformat(), requested_date.isoformat()
    if "지난달" in compact:
        current_month = requested_date.replace(day=1)
        previous_end = current_month - timedelta(days=1)
        return previous_end.replace(day=1).isoformat(), previous_end.isoformat()
    if "이번주" in compact:
        start = requested_date - timedelta(days=requested_date.weekday())
        return start.isoformat(), requested_date.isoformat()
    if "지난주" in compact:
        this_week = requested_date - timedelta(days=requested_date.weekday())
        end = this_week - timedelta(days=1)
        return (end - timedelta(days=6)).isoformat(), end.isoformat()
    if any(marker in compact for marker in ("최근한달", "최근1개월")):
        return (
            _subtract_one_month(requested_date).isoformat(),
            requested_date.isoformat(),
        )
    return None, None


def period_was_mentioned(message: str) -> bool:
    return _EXPLICIT_DATES.search(message) is not None or any(
        marker in message for marker in _PERIOD_MARKERS
    )


def default_recent_month(requested_date: date) -> tuple[str, str]:
    return _subtract_one_month(requested_date).isoformat(), requested_date.isoformat()


def extract_keyword(message: str) -> str | None:
    """가맹점·상대방으로 명시된 `...에서` 표현만 검색어로 추출한다."""

    match = re.search(r"([가-힣A-Za-z0-9]{1,30})에서", message)
    return match.group(1) if match is not None else None


def extract_transaction_type(message: str) -> str | None:
    normalized = message.lower()
    candidates = (
        (("atm", "현금인출"), "atm_withdrawal"),
        (("카드", "결제"), "card_payment"),
        (("수수료",), "fee"),
        (("이자",), "interest"),
        (("송금", "이체"), "transfer"),
        (("입금",), "deposit"),
        (("출금",), "withdrawal"),
    )
    for markers, value in candidates:
        if any(marker in normalized for marker in markers):
            return value
    return None


def extract_summary_type(message: str) -> str | None:
    if any(
        marker in message
        for marker in ("지출", "썼", "쓴", "사용", "결제", "출금")
    ):
        return "spending"
    if any(
        marker in message
        for marker in ("수입", "입금", "들어온", "벌었", "받은")
    ):
        return "income"
    return None


def account_options(raw_accounts: Any) -> list[dict[str, Any]]:
    accounts = raw_accounts if isinstance(raw_accounts, list) else []
    fields = (
        "account_id",
        "bank_name",
        "account_alias",
        "account_type",
        "masked_account_number",
        "currency",
        "is_default",
    )
    return [
        {field: account.get(field) for field in fields}
        for account in accounts
        if isinstance(account, Mapping)
    ]


def _subtract_one_month(value: date) -> date:
    year = value.year if value.month > 1 else value.year - 1
    month = value.month - 1 if value.month > 1 else 12
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)
