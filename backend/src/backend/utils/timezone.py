"""타임존 해석 공통 유틸.

Execution Context 의 timezone 을 기준으로 기간 경계·일일 한도 산정 시각을 계산한다.
"""

from __future__ import annotations

from datetime import timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def resolve_tz(name: str) -> ZoneInfo | timezone:
    """타임존 이름을 해석한다. tzdata 미설치 환경 등 실패 시 UTC 로 안전 대체."""
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return timezone.utc
