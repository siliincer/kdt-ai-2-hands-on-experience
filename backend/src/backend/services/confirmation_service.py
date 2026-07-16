"""Confirmation 생명주기 비즈니스 로직(계약 14·19·21·23장).

    Prepare  → PENDING 생성(승인 대상 고정)
    사용자 승인 → APPROVED
    Execute  → 승인·만료·미실행 재검증 후 EXECUTED
    수정/차단 → INVALIDATED (기존 Confirmation 재사용 불가)

Execute 는 요청 본문의 업무 값이 아니라 `fixed_data` 를 신뢰한다. Agent 는 Execute 에
confirmation_id 만 보내기 때문이다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.agent_exceptions import AgentToolError
from ..models.confirmation import (
    Confirmation,
    ConfirmationOperation,
    ConfirmationStatus,
)
from ..repository.confirmation_repository import (
    create_confirmation,
    get_confirmation_by_id,
    set_confirmation_status,
)
from ..schemas.execution_context import ResolvedExecutionContext
from .agent_tools.policy_constants import CONFIRMATION_TTL_SECONDS


async def create_pending(
    session: AsyncSession,
    context: ResolvedExecutionContext,
    operation: ConfirmationOperation,
    fixed_data: dict[str, Any],
    ttl_seconds: int = CONFIRMATION_TTL_SECONDS,
) -> Confirmation:
    """Prepare 가 판정한 승인 대상을 고정해 PENDING Confirmation 을 만든다."""
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    return await create_confirmation(
        session,
        execution_context_id=context.execution_context_id,
        user_id=context.user_id,
        operation=operation,
        fixed_data=fixed_data,
        expires_at=expires_at,
    )


def _parse_id(raw: str) -> UUID:
    try:
        return UUID(raw)
    except (ValueError, AttributeError) as exc:
        # 형식 오류는 존재 여부를 노출하지 않도록 불일치로 취급한다.
        raise AgentToolError.confirmation_mismatch() from exc


async def load_for_execute(
    session: AsyncSession,
    context: ResolvedExecutionContext,
    confirmation_id: str,
    expected_operation: ConfirmationOperation,
) -> Confirmation:
    """Execute 직전 재검증을 수행하고 승인된 Confirmation 을 반환한다.

    - 미존재/사용자·목적 불일치/이미 소비됨: `CONFIRMATION_MISMATCH` (409)
    - 만료: `CONFIRMATION_EXPIRED` (410)
    - 아직 미승인(PENDING): `CONFIRMATION_REQUIRED` (409)
    """
    confirmation = await get_confirmation_by_id(session, _parse_id(confirmation_id))
    if confirmation is None:
        raise AgentToolError.confirmation_mismatch()
    # 다른 사용자의 Confirmation 은 존재 자체를 알리지 않고 불일치로 처리한다.
    if confirmation.user_id != context.user_id:
        raise AgentToolError.confirmation_mismatch()
    if confirmation.operation is not expected_operation:
        raise AgentToolError.confirmation_mismatch()

    if confirmation.status is ConfirmationStatus.EXPIRED:
        raise AgentToolError.confirmation_expired()
    if confirmation.expires_at <= datetime.now(timezone.utc):
        raise AgentToolError.confirmation_expired()

    if confirmation.status is ConfirmationStatus.PENDING:
        raise AgentToolError.confirmation_required()
    if confirmation.status is not ConfirmationStatus.APPROVED:
        # EXECUTED / INVALIDATED / CANCELLED — 재사용 불가.
        raise AgentToolError.confirmation_mismatch()

    return confirmation


async def approve(session: AsyncSession, confirmation: Confirmation) -> Confirmation:
    """사용자 승인 결과를 저장한다(Backend 가 검증한 뒤에만 호출)."""
    return await set_confirmation_status(
        session,
        confirmation,
        ConfirmationStatus.APPROVED,
        approved_at=datetime.now(timezone.utc),
    )


async def invalidate(session: AsyncSession, confirmation: Confirmation) -> Confirmation:
    """조건 변경·차단으로 기존 Confirmation 을 재사용 불가 처리한다."""
    return await set_confirmation_status(
        session, confirmation, ConfirmationStatus.INVALIDATED
    )


async def mark_executed(
    session: AsyncSession, confirmation: Confirmation
) -> Confirmation:
    """실행 완료 처리. 하나의 Confirmation 은 한 번만 실행될 수 있다."""
    return await set_confirmation_status(
        session,
        confirmation,
        ConfirmationStatus.EXECUTED,
        executed_at=datetime.now(timezone.utc),
    )
