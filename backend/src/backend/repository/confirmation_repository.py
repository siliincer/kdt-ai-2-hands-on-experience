"""Confirmation DB 접근.

상태 전이(승인/무효화/실행 완료)는 서비스가 판단하고, 실제 기록은 여기서 수행한다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, func, select, update
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


async def get_confirmation_by_id(session: AsyncSession, confirmation_id: UUID) -> Confirmation | None:
    """id 로 Confirmation 을 조회한다(없으면 None)."""
    stmt = select(Confirmation).where(Confirmation.id == confirmation_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def has_confirmation_for_execution_context(session: AsyncSession, execution_context_id: UUID) -> bool:
    """이 실행 Context에 Confirmation이 (상태 무관) 한 번이라도 생성됐는지.

    승인 화면까지 한 번이라도 도달했다는 뜻이라, 이후 재입력 화면에서 취소해도
    "변경" 흐름(이전 승인 화면으로 복귀)일 가능성이 높다 — 진짜 최초 취소인지
    판단하는 근거로 쓴다(_is_cancel_input 과 함께, chat_service 참고).
    """
    stmt = select(Confirmation.id).where(Confirmation.execution_context_id == execution_context_id).limit(1)
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


_TRANSFER_OPERATIONS = (
    ConfirmationOperation.INTERNAL_TRANSFER,
    ConfirmationOperation.EXTERNAL_TRANSFER,
)


async def get_executed_transfers_since(session: AsyncSession, user_id: UUID, since: datetime) -> list[Confirmation]:
    """기준 시각 이후 실행 완료된 이체 Confirmation 목록(일일 한도 산정용).

    금액은 Prepare 가 `fixed_data.amount` 에 고정해 두므로 호출부가 합산한다.
    """
    stmt = select(Confirmation).where(
        Confirmation.user_id == user_id,
        Confirmation.status == ConfirmationStatus.EXECUTED,
        Confirmation.operation.in_(_TRANSFER_OPERATIONS),
        Confirmation.executed_at >= since,
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_executed_external_transfers(session: AsyncSession, user_id: UUID) -> list[Confirmation]:
    """사용자의 실행 완료된 타인송금 Confirmation 전체(#5 수취인 자동 확정용, D5).

    수취인 정보(recipient_account_id·recipient_name)는 Prepare 가 `fixed_data` 에
    고정해 두므로 호출부가 이름 정규화·중복 제거를 수행한다.
    """
    stmt = select(Confirmation).where(
        Confirmation.user_id == user_id,
        Confirmation.status == ConfirmationStatus.EXECUTED,
        Confirmation.operation == ConfirmationOperation.EXTERNAL_TRANSFER,
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


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


async def mark_executed_if_approved(session: AsyncSession, confirmation: Confirmation) -> bool:
    """APPROVED→EXECUTED 를 원자적으로 전이한다(C2 동시성).

    조건부 UPDATE 로 한 번만 성공한다. 동시 실행에서 이미 다른 요청이 실행했으면
    rowcount 0 → False 를 반환한다. 하나의 Confirmation 은 한 번만 실행될 수 있다.
    """
    result = cast(
        "CursorResult[Any]",
        await session.execute(
            update(Confirmation)
            .where(
                Confirmation.id == confirmation.id,
                Confirmation.status == ConfirmationStatus.APPROVED,
            )
            .values(status=ConfirmationStatus.EXECUTED, executed_at=func.now())
        ),
    )
    await session.commit()
    if result.rowcount:
        await session.refresh(confirmation)
        return True
    return False
