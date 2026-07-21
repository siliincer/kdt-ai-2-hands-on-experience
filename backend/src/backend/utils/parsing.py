"""식별자 파싱 공통 유틸.

여러 서비스에 흩어져 있던 `_parse_id` / `_parse_account_ids` 를 하나로 모은다.
발생시킬 오류는 호출부가 도메인에 맞게 팩토리로 주입한다(수취인 경로면
`AgentToolError.recipient_not_found`, 승인 경로면 `confirmation_mismatch` 등).

비즈니스 로직과 무관한 순수 helper 라 utils 에 둔다(services 에 의존하지 않음).
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID


def parse_uuid(raw: str | None, on_error: Callable[[], Exception]) -> UUID:
    """문자열을 UUID 로 파싱한다. 누락·형식오류면 `on_error()` 를 던진다."""
    try:
        if raw is None:
            raise ValueError("empty uuid")
        return UUID(raw)
    except (ValueError, AttributeError, TypeError) as exc:
        raise on_error() from exc


def parse_uuid_list(raws: list[str], on_error: Callable[[], Exception]) -> list[UUID]:
    """문자열 목록을 UUID 목록으로 파싱한다. 하나라도 실패하면 `on_error()`."""
    try:
        return [UUID(raw) for raw in raws]
    except (ValueError, AttributeError, TypeError) as exc:
        raise on_error() from exc
