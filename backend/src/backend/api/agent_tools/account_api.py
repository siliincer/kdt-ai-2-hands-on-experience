"""계좌 목록·잔액 조회 Agent Tool API.

- GET  /api/v1/agent-tools/accounts               (API-ACCOUNT-LIST)
- POST /api/v1/agent-tools/accounts/balances:query (API-BALANCE-QUERY)

두 API 모두 서비스 인증 + Execution Context + account:read 스코프를 요구한다.
조회형이라 Idempotency-Key 는 사용하지 않는다(계약 4.1).
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.postgres import get_db
from ...schemas.agent_tools.account import (
    AccountCapability,
    AccountListData,
    BalanceQueryData,
    BalanceQueryRequest,
)
from ...schemas.execution_context import ResolvedExecutionContext
from ...schemas.response import CommonResponse
from ...security.execution_context import require_scope
from ...services.agent_tools import account_service
from ...utils.agent_response import agent_success_response
from ...utils.constants import SCOPE_ACCOUNT_READ

account_router = APIRouter(tags=["Agent Tools - Account"])


@account_router.get("/accounts", response_model=CommonResponse[AccountListData])
async def list_accounts_endpoint(
    account_hint: str | None = Query(default=None, max_length=100),
    account_capability: AccountCapability | None = Query(default=None),
    resolve_selection: bool = Query(default=False),
    all_accounts_requested: bool = Query(default=False),
    exclude_account_ids: list[str] = Query(default=[]),
    limit: int = Query(default=20, ge=1, le=100),
    context: ResolvedExecutionContext = Depends(require_scope(SCOPE_ACCOUNT_READ)),
    session: AsyncSession = Depends(get_db),
):
    """사용자 소유 계좌 후보를 조회한다(마스킹, 잔액 미포함).

    resolve_selection=True 면 계좌 해소 결과(account_resolution_outcome·account_ids)를
    함께 반환한다(계약 9.2). Agent read/transfer 워크플로우의 계좌 확정 관문이다.
    """
    data = await account_service.list_accounts(
        session,
        context,
        account_hint,
        account_capability,
        limit,
        resolve_selection=resolve_selection,
        all_accounts_requested=all_accounts_requested,
        exclude_account_ids=exclude_account_ids,
    )
    return agent_success_response(message="계좌 목록을 조회했습니다.", data=data)


@account_router.post("/accounts/balances:query", response_model=CommonResponse[BalanceQueryData])
async def query_balances_endpoint(
    payload: BalanceQueryRequest,
    context: ResolvedExecutionContext = Depends(require_scope(SCOPE_ACCOUNT_READ)),
    session: AsyncSession = Depends(get_db),
):
    """복수 계좌 잔액을 한 번에 조회한다(소유권 검증 실패 시 전체 거절)."""
    data = await account_service.query_balances(session, context, payload.account_ids)
    return agent_success_response(message="잔액을 조회했습니다.", data=data)
