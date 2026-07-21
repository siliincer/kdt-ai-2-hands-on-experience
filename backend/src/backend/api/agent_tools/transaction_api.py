"""거래내역·기간 합계 Agent Tool API.

- POST /api/v1/agent-tools/transactions:query   (API-TRANSACTION-QUERY)
- POST /api/v1/agent-tools/transactions:summary (API-TRANSACTION-SUMMARY)

서비스 인증 + Execution Context + account:read 스코프를 요구한다. 조회형이라
Idempotency-Key 는 사용하지 않는다(계약 4.1).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.postgres import get_db
from ...schemas.agent_tools.transaction import (
    TransactionQueryData,
    TransactionQueryRequest,
    TransactionSummaryData,
    TransactionSummaryRequest,
)
from ...schemas.execution_context import ResolvedExecutionContext
from ...schemas.response import CommonResponse
from ...security.execution_context import require_scope
from ...services.agent_tools import transaction_service
from ...utils.agent_response import agent_success_response
from ...utils.constants import SCOPE_ACCOUNT_READ

transaction_router = APIRouter(tags=["Agent Tools - Transaction"])


@transaction_router.post(
    "/transactions:query", response_model=CommonResponse[TransactionQueryData]
)
async def query_transactions_endpoint(
    payload: TransactionQueryRequest,
    context: ResolvedExecutionContext = Depends(require_scope(SCOPE_ACCOUNT_READ)),
    session: AsyncSession = Depends(get_db),
):
    """거래내역 첫 페이지를 조회한다(계좌 병합·전역 정렬, 소유권 실패 시 전체 거절)."""
    data = await transaction_service.query_transactions(session, context, payload)
    return agent_success_response(message="거래내역을 조회했습니다.", data=data)


@transaction_router.post(
    "/transactions:summary", response_model=CommonResponse[TransactionSummaryData]
)
async def summarize_transactions_endpoint(
    payload: TransactionSummaryRequest,
    context: ResolvedExecutionContext = Depends(require_scope(SCOPE_ACCOUNT_READ)),
    session: AsyncSession = Depends(get_db),
):
    """기간 내 지출/수입 합계를 조회한다."""
    data = await transaction_service.summarize_transactions(session, context, payload)
    return agent_success_response(message="거래 합계를 조회했습니다.", data=data)
