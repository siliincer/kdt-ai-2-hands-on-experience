"""추가 인증 Context 생성 Agent Tool API (#7).

- POST /api/v1/agent-tools/auth-contexts (API-AUTH-CONTEXT-CREATE)

상태 변경 API 라 `Idempotency-Key` 헤더가 필수다(계약 4.2·24.1). 독립된 Context 리소스를
생성하므로 성공 시 **201 Created** 를 반환한다(계약 5.4).

인증 Assertion·PIN·생체인증 결과 원문은 Agent 에 반환하지 않는다(계약 15.4).
"""

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.postgres import get_db
from ...schemas.agent_tools.auth_context import (
    AuthContextCreateData,
    AuthContextCreateRequest,
)
from ...schemas.execution_context import ResolvedExecutionContext
from ...schemas.response import CommonResponse
from ...security.execution_context import require_scope
from ...services.agent_tools import auth_tool_service
from ...utils.constants import SCOPE_TRANSFER_REQUEST
from .idempotent_runner import run_idempotent

auth_context_router = APIRouter(tags=["Agent Tools - Auth Context"])

_IdempotencyHeader = Header(default=None, alias="Idempotency-Key")

_CREATED = 201


@auth_context_router.post(
    "/auth-contexts",
    response_model=CommonResponse[AuthContextCreateData],
    response_model_exclude_none=True,
    status_code=_CREATED,
)
async def create_auth_context_endpoint(
    payload: AuthContextCreateRequest,
    idempotency_key: str | None = _IdempotencyHeader,
    context: ResolvedExecutionContext = Depends(require_scope(SCOPE_TRANSFER_REQUEST)),
    session: AsyncSession = Depends(get_db),
):
    """승인된 이체 Confirmation 에 대한 추가 인증을 준비한다."""
    return await run_idempotent(
        session,
        context,
        "auth_context_create",
        idempotency_key,
        payload,
        "추가 인증을 준비했습니다.",
        lambda: auth_tool_service.create_auth_context(session, context, payload),
        success_status=_CREATED,
    )
