from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.schemas.ui import (
    BalanceData,
    BudgetData,
    CardsData,
    SpendingData,
    TransactionsData,
)
from backend.services.mock.mock_agent_driver import _match_component
from backend.services.ui_service import (
    get_balance_view,
    get_budget_view,
    get_cards_view,
    get_spending_view,
    get_transactions_view,
)


def test_match_component_detects_balance_intent():
    assert _match_component("내 잔액 알려줘") == "balance"
    assert _match_component("총 자산 얼마야") == "balance"
    assert _match_component("송금하고 싶어") is None


def test_match_component_detects_new_card_intents():
    assert _match_component("이번 달 소비 분석해줘") == "spending"
    assert _match_component("거래 내역 보여줘") == "transactions"
    assert _match_component("예산 현황 알려줘") == "budget"
    assert _match_component("카드 청구서 보여줘") == "cards"


@pytest.mark.asyncio
async def test_get_balance_view_returns_balance_data():
    data = await get_balance_view(uuid4())
    assert isinstance(data, BalanceData)
    assert data.total == sum(a.balance for a in data.accounts)
    assert len(data.accounts) >= 1


@pytest.mark.asyncio
async def test_get_spending_view_returns_spending_data():
    data = await get_spending_view(uuid4())
    assert isinstance(data, SpendingData)
    assert len(data.pie) >= 1
    assert len(data.bar) >= 1
    assert set(data.catTx).issubset({p.name for p in data.pie})


@pytest.mark.asyncio
async def test_get_transactions_view_filters_by_month():
    all_tx = await get_transactions_view(uuid4())
    assert isinstance(all_tx, TransactionsData)
    assert len(all_tx.items) >= 1

    june = await get_transactions_view(uuid4(), "2025-06")
    assert len(june.items) >= 1
    assert all(tx.month == "2025-06" for tx in june.items)
    assert len(june.items) < len(all_tx.items)


@pytest.mark.asyncio
async def test_get_budget_view_returns_budget_data():
    data = await get_budget_view(uuid4())
    assert isinstance(data, BudgetData)
    assert len(data.budgetItems) >= 1
    assert len(data.subItems) >= 1


@pytest.mark.asyncio
async def test_get_cards_view_returns_cards_data():
    data = await get_cards_view(uuid4())
    assert isinstance(data, CardsData)
    assert len(data.cards) >= 1


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/ui/balance",
        "/api/v1/ui/spending",
        "/api/v1/ui/transactions",
        "/api/v1/ui/budget",
        "/api/v1/ui/cards",
    ],
)
def test_ui_endpoints_require_auth(client: TestClient, path: str):
    response = client.get(path)
    assert response.status_code in (401, 403)
