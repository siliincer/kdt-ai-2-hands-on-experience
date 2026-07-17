"""ISO8601 파싱 공통 유틸.

계정계(mock-financial-service)가 반환하는 ISO8601 문자열을 파싱한다. 여러 서비스에
흩어져 있던 `_parse_dt` 를 하나로 모은다. 순수 helper 라 utils 에 둔다.
"""

from __future__ import annotations

from datetime import datetime, timezone


def parse_iso_utc(value: str) -> datetime:
    """ISO8601(Z 포함 가능) 파싱. tz 정보가 없으면 UTC 로 간주한다.

    naive datetime 을 그대로 두면 이후 astimezone 등에서 오류가 나므로, 안전하게
    UTC 를 붙인다(계정계 응답엔 보통 offset 이 있어 이 분기는 드물다).
    """
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
