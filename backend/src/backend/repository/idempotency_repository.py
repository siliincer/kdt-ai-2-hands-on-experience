"""멱등성 레코드 DB 접근(계약 24장).

고유성 기준은 (execution_context_id, operation, idempotency_key).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.idempotency_key import IdempotencyKey, IdempotencyStatus


async def get_idempotency_record(
    session: AsyncSession,
    execution_context_id: UUID,
    operation: str,
    idempotency_key: str,
) -> IdempotencyKey | None:
    """같은 Context·Operation·Key 의 기존 레코드를 조회한다."""
    stmt = select(IdempotencyKey).where(
        IdempotencyKey.execution_context_id == execution_context_id,
        IdempotencyKey.operation == operation,
        IdempotencyKey.idempotency_key == idempotency_key,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_in_progress(
    session: AsyncSession,
    execution_context_id: UUID,
    operation: str,
    idempotency_key: str,
    request_hash: str,
    expires_at: datetime,
) -> IdempotencyKey:
    """키를 IN_PROGRESS 로 선점한다(계약 24.5의 '멱등성 키 선점')."""
    record = IdempotencyKey(
        execution_context_id=execution_context_id,
        operation=operation,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        status=IdempotencyStatus.IN_PROGRESS,
        expires_at=expires_at,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


async def complete_idempotency(
    session: AsyncSession,
    record: IdempotencyKey,
    response_status: int,
    response_body: dict[str, Any],
) -> IdempotencyKey:
    """처리 결과를 저장해 이후 같은 키 재호출이 최초 응답을 복원하게 한다."""
    record.status = IdempotencyStatus.COMPLETED
    record.response_status = response_status
    record.response_body = response_body
    await session.commit()
    await session.refresh(record)
    return record
