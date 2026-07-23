"""일반 입력 대기(pending_input) DB 접근(UI-HITL 계약 1.3·1.5)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.pending_input import (
    PENDING_INPUT_STATUS_ACTIVE,
    PENDING_INPUT_STATUS_CANCELLED,
    PENDING_INPUT_STATUS_CONSUMED,
    PendingInput,
)


async def create_pending_input(
    session: AsyncSession,
    input_request_id: str,
    chat_session_id: UUID,
    ui_contract_id: str,
    ui_type: str,
    expires_at: datetime,
    execution_context_id: UUID | None = None,
    agent_thread_id: str | None = None,
) -> PendingInput:
    """새 입력 대기(active)를 생성한다."""
    pending = PendingInput(
        input_request_id=input_request_id,
        chat_session_id=chat_session_id,
        ui_contract_id=ui_contract_id,
        ui_type=ui_type,
        expires_at=expires_at,
        execution_context_id=execution_context_id,
        agent_thread_id=agent_thread_id,
    )
    session.add(pending)
    await session.commit()
    await session.refresh(pending)
    return pending


async def get_pending_input_by_request_id(session: AsyncSession, input_request_id: str) -> PendingInput | None:
    """input_request_id 로 대기 행을 조회한다(없으면 None).

    소유권·상태 검증은 서비스가 담당한다. 같은 id 재사용은 없다고 보고 최신 1건을 본다.
    """
    stmt = (
        select(PendingInput)
        .where(PendingInput.input_request_id == input_request_id)
        .order_by(PendingInput.created_at.desc())
    )
    result = await session.execute(stmt)
    return result.scalars().first()


async def cancel_active_pending_inputs(session: AsyncSession, chat_session_id: UUID) -> int:
    """해당 chat_session 의 활성 대기를 모두 cancelled 로 무효화한다(계약 1.3).

    한 세션에 동시 활성 대기 1개 규약을 위해 새 대기 등록 직전에 호출한다.
    """
    result = cast(
        "CursorResult[Any]",
        await session.execute(
            update(PendingInput)
            .where(
                PendingInput.chat_session_id == chat_session_id,
                PendingInput.status == PENDING_INPUT_STATUS_ACTIVE,
            )
            .values(status=PENDING_INPUT_STATUS_CANCELLED)
        ),
    )
    await session.commit()
    return int(result.rowcount or 0)


async def mark_pending_input_consumed(session: AsyncSession, pending: PendingInput, consumed_at: datetime) -> bool:
    """대기 행을 원자적으로 소비 처리한다(동시 제출 방지).

    active→consumed 조건부 UPDATE 로 한 번만 성공한다. 동시 제출에서 이미 다른 요청이
    소비했으면 rowcount 0 → False. 하나의 대기는 한 번만 소비될 수 있다.
    """
    result = cast(
        "CursorResult[Any]",
        await session.execute(
            update(PendingInput)
            .where(
                PendingInput.id == pending.id,
                PendingInput.status == PENDING_INPUT_STATUS_ACTIVE,
            )
            .values(status=PENDING_INPUT_STATUS_CONSUMED, consumed_at=consumed_at)
        ),
    )
    await session.commit()
    return bool(result.rowcount)
