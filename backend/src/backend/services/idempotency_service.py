"""멱등성 처리(계약 24장).

상태 변경 API(Prepare/Auth/Execute)에만 적용한다. 사용 흐름:

    replay = await begin(session, context, operation, key, request_hash)
    if replay is not None:          # 이미 완료된 같은 요청 → 최초 응답 복원
        return replay.to_response()
    ...실제 처리...
    await complete(session, context, operation, key, status_code, body)

- 같은 키 + 같은 Body + COMPLETED → 최초 status/body 반환
- 같은 키 + 다른 Body        → IDEMPOTENCY_KEY_CONFLICT (409)
- 같은 키 + 처리 중          → IDEMPOTENCY_REQUEST_IN_PROGRESS (409, Retry-After)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.agent_exceptions import AgentToolError
from ..models.idempotency_key import IdempotencyStatus
from ..repository.idempotency_repository import (
    complete_idempotency,
    create_in_progress,
    get_idempotency_record,
)
from ..schemas.execution_context import ResolvedExecutionContext
from .agent_tools.policy_constants import IDEMPOTENCY_TTL_SECONDS


@dataclass
class IdempotentReplay:
    """이미 완료된 동일 요청의 최초 응답."""

    status_code: int
    body: dict[str, Any]

    def to_response(self) -> JSONResponse:
        return JSONResponse(status_code=self.status_code, content=self.body)


def compute_request_hash(payload: Any) -> str:
    """정규화한 요청 Body 의 sha256(계약 24.3).

    키 정렬 + 공백 제거로 같은 의미의 Body 가 같은 해시를 갖게 한다.
    """
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def require_key(idempotency_key: str | None) -> str:
    """상태 변경 API 의 필수 헤더 검증(계약 4.2)."""
    if not idempotency_key or not idempotency_key.strip():
        raise AgentToolError.missing_idempotency_key()
    return idempotency_key.strip()


async def begin(
    session: AsyncSession,
    context: ResolvedExecutionContext,
    operation: str,
    idempotency_key: str,
    request_hash: str,
) -> IdempotentReplay | None:
    """키를 선점하거나, 이미 완료된 동일 요청이면 최초 응답을 돌려준다."""
    existing = await get_idempotency_record(
        session, context.execution_context_id, operation, idempotency_key
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise AgentToolError.idempotency_key_conflict()
        if existing.status is IdempotencyStatus.COMPLETED:
            return IdempotentReplay(
                status_code=existing.response_status or 200,
                body=existing.response_body or {},
            )
        # IN_PROGRESS — 아직 처리 중이므로 Retry-After 후 같은 키로 재호출.
        raise AgentToolError.idempotency_request_in_progress()

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=IDEMPOTENCY_TTL_SECONDS)
    try:
        await create_in_progress(
            session,
            execution_context_id=context.execution_context_id,
            operation=operation,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            expires_at=expires_at,
        )
    except IntegrityError as exc:
        # C1(동시성): 같은 순간 다른 요청이 같은 키를 방금 선점(유니크 제약 위반).
        # 500 대신 '처리 중'으로 번역해 Retry-After 후 재호출하게 한다.
        # 실패한 트랜잭션은 상위 get_db 예외 경로에서 rollback 된다.
        raise AgentToolError.idempotency_request_in_progress() from exc
    return None


async def complete(
    session: AsyncSession,
    context: ResolvedExecutionContext,
    operation: str,
    idempotency_key: str,
    status_code: int,
    body: dict[str, Any],
) -> None:
    """처리 결과를 저장한다. 선점 레코드가 없으면 조용히 넘어간다."""
    record = await get_idempotency_record(
        session, context.execution_context_id, operation, idempotency_key
    )
    if record is None:
        return
    await complete_idempotency(session, record, status_code, body)
