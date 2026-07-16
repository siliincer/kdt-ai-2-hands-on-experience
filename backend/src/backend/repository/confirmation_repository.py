"""Confirmation DB 접근.

상태 전이(승인/무효화/실행 완료)는 서비스가 판단하고, 실제 기록은 여기서 수행한다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.confirmation import (
    Confirmation,
    ConfirmationOperation,
    ConfirmationStatus,
)


async def create_confirmation(
    session: AsyncSession,
    execution_context_id: UUID,
    user_id: UUID,
    operation: ConfirmationOperation,
    fixed_data: dict[str, Any],
    expires_at: datetime,
) -> Confirmation:
    """Prepare 결과를 고정한 PENDING Confirmation 을 생성한다."""
    confirmation = Confirmation(
        execution_context_id=execution_context_id,
        user_id=user_id,
        operation=operation,
        fixed_data=fixed_data,
        expires_at=expires_at,
        status=ConfirmationStatus.PENDING,
    )
    session.add(confirmation)
    await session.commit()
    await session.refresh(confirmation)
    return confirmation


async def get_confirmation_by_id(
    session: AsyncSession, confirmation_id: UUID
) -> Confirmation | None:
    """id 로 Confirmation 을 조회한다(없으면 None)."""
    stmt = select(Confirmation).where(Confirmation.id == confirmation_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def set_confirmation_status(
    session: AsyncSession,
    confirmation: Confirmation,
    status: ConfirmationStatus,
    approved_at: datetime | None = None,
    executed_at: datetime | None = None,
) -> Confirmation:
    """Confirmation 상태를 전이시키고 저장한다."""
    confirmation.status = status
    if approved_at is not None:
        confirmation.approved_at = approved_at
    if executed_at is not None:
        confirmation.executed_at = executed_at
    await session.commit()
    await session.refresh(confirmation)
    return confirmation
