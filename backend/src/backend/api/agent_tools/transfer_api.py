"""이체 Agent Tool API (#9·#10, Stage 6 에서 타인송금 추가 예정).

경로는 모두 `/api/v1/agent-tools` prefix 아래에 있다.

- POST /transfers/internal:prepare (API-INTERNAL-TRANSFER-PREPARE)
- POST /transfers/internal         (API-INTERNAL-TRANSFER-EXECUTE)

상태 변경 API 라 `Idempotency-Key` 헤더가 필수다(계약 4.2·24.1).
"""

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.postgres import get_db
from ...schemas.agent_tools.transfer import (
    InternalTransferPrepareData,
    InternalTransferPrepareRequest,
    TransferExecuteData,
    TransferExecuteRequest,
)
from ...schemas.execution_context import ResolvedExecutionContext
from ...schemas.response import CommonResponse
from ...security.execution_context import require_scope
from ...services.agent_tools import transfer_service
from ...utils.constants import SCOPE_TRANSFER_REQUEST
from .idempotent_runner import run_idempotent

transfer_router = APIRouter(tags=["Agent Tools - Transfer"])

_IdempotencyHeader = Header(default=None, alias="Idempotency-Key")


@transfer_router.post(
    "/transfers/internal:prepare",
    response_model=CommonResponse[InternalTransferPrepareData],
    response_model_exclude_none=True,
)
async def prepare_internal_transfer_endpoint(
    payload: InternalTransferPrepareRequest,
    idempotency_key: str | None = _IdempotencyHeader,
    context: ResolvedExecutionContext = Depends(require_scope(SCOPE_TRANSFER_REQUEST)),
    session: AsyncSession = Depends(get_db),
):
    """본인 계좌 간 이체 조건을 평가한다(ready/correction)."""
    return await run_idempotent(
        session,
        context,
        "internal_transfer_prepare",
        idempotency_key,
        payload,
        "이체 요청을 확인했습니다.",
        lambda: transfer_service.prepare_internal_transfer(session, context, payload),
    )


@transfer_router.post(
    "/transfers/internal",
    response_model=CommonResponse[TransferExecuteData],
    response_model_exclude_none=True,
)
async def execute_internal_transfer_endpoint(
    payload: TransferExecuteRequest,
    idempotency_key: str | None = _IdempotencyHeader,
    context: ResolvedExecutionContext = Depends(require_scope(SCOPE_TRANSFER_REQUEST)),
    session: AsyncSession = Depends(get_db),
):
    """승인 + 추가 인증이 끝난 본인 계좌 간 이체를 실행한다."""
    return await run_idempotent(
        session,
        context,
        "internal_transfer_execute",
        idempotency_key,
        payload,
        "계좌 이체가 완료되었습니다.",
        lambda: transfer_service.execute_internal_transfer(session, context, payload),
    )
