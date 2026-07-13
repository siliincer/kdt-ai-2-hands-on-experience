from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.postgres import get_db
from ..models.user import User
from ..schemas.response import CommonResponse
from ..schemas.ui import (
    AccountDetailData,
    BalanceData,
    BudgetData,
    CardsData,
    SpendingData,
    TransactionsData,
)
from ..security.jwt import get_current_user
from ..services.ui_service import (
    get_account_detail_view,
    get_balance_view,
    get_budget_view,
    get_cards_view,
    get_spending_view,
    get_transactions_view,
)
from ..utils.build_response import success_response

ui_router = APIRouter(prefix="/ui", tags=["UI Data"])


@ui_router.get("/balance", response_model=CommonResponse[BalanceData])
async def read_balance(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """자산 현황 카드 데이터 (component:balance 시그널 후 FE 가 조회, ADR-002)."""
    data = await get_balance_view(current_user.id, session)
    return success_response(message="자산 현황을 조회했습니다.", data=data)


@ui_router.get(
    "/account/{account_id}", response_model=CommonResponse[AccountDetailData]
)
async def read_account_detail(
    account_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """계좌 상세 카드 데이터 (component:account_detail, B2).

    잔액 + 최근 거래를 돌려준다. account_id 는 user 소유 계좌여야 하며,
    아니면 404. recent[].amount 는 부호를 가진다(A2 거래내역과 규칙 다름).
    """
    data = await get_account_detail_view(current_user.id, account_id, session)
    return success_response(message="계좌 상세를 조회했습니다.", data=data)


@ui_router.get("/spending", response_model=CommonResponse[SpendingData])
async def read_spending(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """소비 분석 카드 데이터 (component:spending 시그널 후 FE 가 조회)."""
    data = await get_spending_view(current_user.id, session)
    return success_response(message="소비 분석을 조회했습니다.", data=data)


@ui_router.get("/transactions", response_model=CommonResponse[TransactionsData])
async def read_transactions(
    month: str | None = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """거래 내역 카드 데이터 (component:transactions 시그널 후 FE 가 조회).

    쿼리 `month`(예: 2025-06)로 특정 월만 조회할 수 있다(생략 시 전체).
    """
    data = await get_transactions_view(current_user.id, month, session)
    return success_response(message="거래 내역을 조회했습니다.", data=data)


@ui_router.get("/budget", response_model=CommonResponse[BudgetData])
async def read_budget(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """예산 현황 카드 데이터 (component:budget 시그널 후 FE 가 조회)."""
    data = await get_budget_view(current_user.id, session)
    return success_response(message="예산 현황을 조회했습니다.", data=data)


@ui_router.get("/cards", response_model=CommonResponse[CardsData])
async def read_cards(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """카드 관리 카드 데이터 (component:cards 시그널 후 FE 가 조회)."""
    data = await get_cards_view(current_user.id, session)
    return success_response(message="카드 정보를 조회했습니다.", data=data)
