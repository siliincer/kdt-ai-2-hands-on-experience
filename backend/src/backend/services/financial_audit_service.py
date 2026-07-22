"""금융 감사 로그 기록(계약 25장).

정본 주체는 Backend 다. Agent 가 `write_audit_log` 를 호출하는 구조는 사용하지 않고,
각 금융 API 가 처리 과정에서 직접 이 서비스를 호출해 Audit Event 를 남긴다.

Execution Context 에서 사용자·세션·스레드를 채우므로 호출부는 업무 필드만 넘긴다.
민감정보(전체 계좌번호·잔액 원문·인증 원문·토큰)는 넘기지 않는다(계약 25.3).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.request_context import get_request_id
from ..models.financial_audit_log import FinancialAuditLog
from ..repository.financial_audit_repository import create_financial_audit_log
from ..schemas.execution_context import ResolvedExecutionContext


async def record(
    session: AsyncSession,
    context: ResolvedExecutionContext,
    event_type: str,
    operation: str,
    outcome: str,
    contract_id: str | None = None,
    confirmation_id: UUID | None = None,
    auth_context_id: UUID | None = None,
    transaction_id: str | None = None,
    idempotency_key: str | None = None,
    reason: str | None = None,
    policy_codes: list[str] | None = None,
    request_id: str | None = None,
    actor_type: str = "agent_service",
) -> FinancialAuditLog:
    """감사 이벤트 1건을 기록한다(실행 Context 로 주체 정보를 채움).

    `request_id` 를 넘기지 않으면 현재 요청에 바인딩된 `X-Request-Id` 를 사용한다
    (Agent 로그와 같은 값으로 감사 추적을 잇는다).
    """
    return await create_financial_audit_log(
        session,
        user_id=context.user_id,
        event_type=event_type,
        operation=operation,
        outcome=outcome,
        actor_type=actor_type,
        request_id=request_id or get_request_id(),
        execution_context_id=context.execution_context_id,
        chat_session_id=context.chat_session_id,
        agent_thread_id=context.agent_thread_id,
        contract_id=contract_id,
        confirmation_id=confirmation_id,
        auth_context_id=auth_context_id,
        transaction_id=transaction_id,
        idempotency_key=idempotency_key,
        reason=reason,
        policy_codes=policy_codes,
    )
