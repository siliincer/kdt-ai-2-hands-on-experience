"""금융 감사 로그 DB 접근(계약 25장).

append-only: insert 만 제공하고 update/delete 함수를 두지 않는다.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.financial_audit_log import FinancialAuditLog


async def create_financial_audit_log(
    session: AsyncSession,
    user_id: UUID,
    event_type: str,
    operation: str,
    outcome: str,
    actor_type: str = "agent_service",
    request_id: str | None = None,
    execution_context_id: UUID | None = None,
    chat_session_id: UUID | None = None,
    agent_thread_id: str | None = None,
    contract_id: str | None = None,
    confirmation_id: UUID | None = None,
    auth_context_id: UUID | None = None,
    transaction_id: str | None = None,
    idempotency_key: str | None = None,
    reason: str | None = None,
    policy_codes: list[str] | None = None,
) -> FinancialAuditLog:
    """감사 이벤트 1건을 기록한다."""
    log = FinancialAuditLog(
        user_id=user_id,
        event_type=event_type,
        operation=operation,
        outcome=outcome,
        actor_type=actor_type,
        request_id=request_id,
        execution_context_id=execution_context_id,
        chat_session_id=chat_session_id,
        agent_thread_id=agent_thread_id,
        contract_id=contract_id,
        confirmation_id=confirmation_id,
        auth_context_id=auth_context_id,
        transaction_id=transaction_id,
        idempotency_key=idempotency_key,
        reason=reason,
        policy_codes=policy_codes,
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)
    return log
