"""추가 인증 Context 생성 Tool 로직 (#7, 계약 15장).

Agent 는 승인된 Confirmation 의 id 만 보낸다. 송금 유형·사용자·송금 조건은 이미
Confirmation 에 고정되어 있으므로 purpose·user_id 를 중복 전달받지 않는다.

Agent 는 이 응답으로 `authentication_required` Webhook 을 보내고 Workflow 를 중단한다.
이후 Frontend 인증 → Backend 검증 → Agent 재개는 Stage 7 에서 연결한다.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ...models.financial_audit_log import EVENT_AUTH_CONTEXT_CREATED
from ...schemas.agent_tools.auth_context import (
    AuthContextCreateData,
    AuthContextCreateRequest,
    AuthOutcome,
    AuthRequestView,
)
from ...schemas.execution_context import ResolvedExecutionContext
from .. import auth_context_service, confirmation_service, financial_audit_service

_CONTRACT_AUTH_CREATE = "API-AUTH-CONTEXT-CREATE"
_OP_AUTH_CREATE = "auth_context_create"

_AUTH_TITLE = "추가 인증이 필요합니다."
_AUTH_DESCRIPTION = "송금을 계속하려면 본인 인증을 완료해 주세요."


async def create_auth_context(
    session: AsyncSession,
    context: ResolvedExecutionContext,
    req: AuthContextCreateRequest,
) -> AuthContextCreateData:
    """승인된 이체 Confirmation 에 대한 추가 인증을 준비한다.

    Confirmation 이 승인 상태가 아니거나 만료면 Confirmation 계열 오류로 거부한다.
    설정 변경 Confirmation 은 추가 인증 대상이 아니라 불일치로 거부한다(계약 19.3).
    """
    confirmation = await confirmation_service.load_for_auth(session, context, req.confirmation_id)
    auth_context = await auth_context_service.create_for_confirmation(session, context, confirmation)
    await financial_audit_service.record(
        session,
        context,
        event_type=EVENT_AUTH_CONTEXT_CREATED,
        operation=_OP_AUTH_CREATE,
        outcome=AuthOutcome.AUTHENTICATION_REQUIRED,
        contract_id=_CONTRACT_AUTH_CREATE,
        confirmation_id=confirmation.id,
        auth_context_id=auth_context.id,
    )
    return AuthContextCreateData(
        outcome=AuthOutcome.AUTHENTICATION_REQUIRED,
        auth_context_id=str(auth_context.id),
        auth_request_view=AuthRequestView(
            title=_AUTH_TITLE,
            description=_AUTH_DESCRIPTION,
            available_methods=list(auth_context.available_methods),
            expires_at=auth_context.expires_at,
        ),
    )
