"""수취인 자동 확정 Agent Tool API (#5).

- POST /api/v1/agent-tools/recipients:resolve (API-RECIPIENT-RESOLVE)

조회형이라 Idempotency-Key 는 사용하지 않는다(계약 13.1: 상태 변경 없음).
후보 목록·수취인 이름은 반환하지 않는다 — resolved 또는 selection_required 판단만.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.postgres import get_db
from ...schemas.agent_tools.recipient import (
    RecipientResolveData,
    RecipientResolveRequest,
)
from ...schemas.execution_context import ResolvedExecutionContext
from ...schemas.response import CommonResponse
from ...security.execution_context import require_scope
from ...services.agent_tools import recipient_service
from ...utils.agent_response import agent_success_response
from ...utils.constants import SCOPE_TRANSFER_REQUEST

recipient_router = APIRouter(tags=["Agent Tools - Recipient"])


@recipient_router.post(
    "/recipients:resolve",
    response_model=CommonResponse[RecipientResolveData],
    response_model_exclude_none=True,
)
async def resolve_recipient_endpoint(
    payload: RecipientResolveRequest,
    context: ResolvedExecutionContext = Depends(require_scope(SCOPE_TRANSFER_REQUEST)),
    session: AsyncSession = Depends(get_db),
):
    """이름 힌트를 기존 거래 수취인 하나로 자동 확정할 수 있는지 판단한다."""
    data = await recipient_service.resolve_recipient(session, context, payload)
    message = "기존 거래 수취인을 확인했습니다." if data.outcome == "resolved" else "수취인 선택이 필요합니다."
    return agent_success_response(message=message, data=data)
