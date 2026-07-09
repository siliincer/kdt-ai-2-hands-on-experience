"""UI Data API 비즈니스 로직 (BFF, ADR-002).

FE 가 component 시그널을 받은 뒤 카드 데이터를 조회하는 계층.
현재는 목 픽스처를 반환한다. 향후 정보계(postgres/redis) 및
mock-financial-service(계정계) 조회로 교체한다.
"""

from uuid import UUID

from ..schemas.ui import (
    BalanceData,
    BudgetData,
    CardsData,
    SpendingData,
    TransactionsData,
)
from .mock.ui_fixtures import (
    BALANCE_FIXTURE,
    BUDGET_FIXTURE,
    CARDS_FIXTURE,
    SPENDING_FIXTURE,
    TRANSACTIONS_FIXTURE,
)


async def get_balance_view(user_id: UUID) -> BalanceData:
    """사용자 자산 현황 view model.

    TODO: mock-financial-service(계정계) 잔액 조회 + 정보계 캐시로 교체.
    """
    # 현재는 유저 무관 목 데이터
    _ = user_id
    return BALANCE_FIXTURE


async def get_spending_view(user_id: UUID) -> SpendingData:
    """소비 분석 view model. TODO: 정보계 집계로 교체."""
    _ = user_id
    return SPENDING_FIXTURE


async def get_transactions_view(
    user_id: UUID, month: str | None = None
) -> TransactionsData:
    """거래 내역 view model.

    month 가 주어지면 해당 월만 필터링(예: '2025-06'). TODO: 정보계 조회로 교체.
    """
    _ = user_id
    if month is None:
        return TRANSACTIONS_FIXTURE
    items = [tx for tx in TRANSACTIONS_FIXTURE.items if tx.month == month]
    return TransactionsData(months=TRANSACTIONS_FIXTURE.months, items=items)


async def get_budget_view(user_id: UUID) -> BudgetData:
    """예산 현황 view model. TODO: 정보계 조회로 교체."""
    _ = user_id
    return BUDGET_FIXTURE


async def get_cards_view(user_id: UUID) -> CardsData:
    """카드 관리 view model. TODO: 계정계(카드사) 조회로 교체."""
    _ = user_id
    return CARDS_FIXTURE
