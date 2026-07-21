from types import SimpleNamespace
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
from backend.services import ui_service
from backend.services.mock.mock_agent_driver import _match_component
from backend.services.ui_service import (
    get_balance_view,
    get_budget_view,
    get_cards_view,
    get_spending_view,
    get_transactions_view,
)

# 계정계 http 일원화(작업 B) 이후 UI 뷰는 계정계 원장/잔액을 실조회한다. 테스트는
# repository 조회를 monkeypatch 로, 계정계 응답을 financial_stub(MockTransport)로 대체한다.
_SESSION = object()  # http 경로는 세션을 repository 로만 넘기므로 sentinel 로 충분


def _patch_mapped(monkeypatch, rows):
    async def _fetch(session, user_id):
        return rows

    monkeypatch.setattr(ui_service, "get_mapped_accounts", _fetch)


def _patch_ext_ids(monkeypatch, ids):
    async def _fetch(session, user_id):
        return ids

    monkeypatch.setattr(ui_service, "get_external_account_ids", _fetch)


def _entry(created_at: str, entry_type: str, amount: int) -> dict:
    return {"created_at": created_at, "entry_type": entry_type, "amount": amount}


# ── mock 드라이버 component 매칭(참고용 유틸) ────────────────────────────────


def test_match_component_detects_balance_intent():
    assert _match_component("내 잔액 알려줘") == "balance"
    assert _match_component("총 자산 얼마야") == "balance"
    assert _match_component("송금하고 싶어") is None


def test_match_component_detects_new_card_intents():
    assert _match_component("이번 달 소비 분석해줘") == "spending"
    assert _match_component("거래 내역 보여줘") == "transactions"
    assert _match_component("예산 현황 알려줘") == "budget"
    assert _match_component("카드 청구서 보여줘") == "cards"


# ── UI 뷰(계정계 원장 실조회) ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_balance_view_sums_account_balances(monkeypatch, financial_stub):
    _patch_mapped(
        monkeypatch,
        [
            SimpleNamespace(
                external_account_id="ext-1",
                bank_name="KDT은행",
                account_number="333-12-1234567",
            )
        ],
    )
    financial_stub.balances["ext-1"] = {
        "account_id": "ext-1",
        "balance": 5000,
        "currency": "KRW",
    }

    data = await get_balance_view(uuid4(), session=_SESSION)

    assert isinstance(data, BalanceData)
    assert len(data.accounts) == 1
    assert data.total == 5000
    assert data.total == sum(a.balance for a in data.accounts)


@pytest.mark.asyncio
async def test_get_transactions_view_filters_by_month(monkeypatch, financial_stub):
    _patch_ext_ids(monkeypatch, ["ext-1"])
    financial_stub.ledgers["ext-1"] = [
        _entry("2025-07-02T10:00:00+00:00", "DEBIT", 3000),
        _entry("2025-06-15T09:00:00+00:00", "DEBIT", 5000),
        _entry("2025-06-20T09:00:00+00:00", "CREDIT", 7000),
    ]

    all_tx = await get_transactions_view(uuid4(), session=_SESSION)
    assert isinstance(all_tx, TransactionsData)
    assert len(all_tx.items) == 3

    june = await get_transactions_view(uuid4(), "2025-06", session=_SESSION)
    assert len(june.items) == 2
    assert all(tx.month == "2025-06" for tx in june.items)
    assert len(june.items) < len(all_tx.items)


@pytest.mark.asyncio
async def test_get_spending_view_aggregates_debits(monkeypatch, financial_stub):
    _patch_ext_ids(monkeypatch, ["ext-1"])
    financial_stub.ledgers["ext-1"] = [
        _entry("2025-06-15T09:00:00+00:00", "DEBIT", 5000),
        _entry("2025-06-20T09:00:00+00:00", "CREDIT", 7000),
    ]

    data = await get_spending_view(uuid4(), session=_SESSION)

    assert isinstance(data, SpendingData)
    # 카테고리 원천이 없어 단일 '기타' 버킷 + bar 는 빈 리스트(정직한 제한).
    assert len(data.pie) == 1
    assert data.pie[0].amount == 5000
    assert data.bar == []
    assert set(data.catTx).issubset({p.name for p in data.pie})


@pytest.mark.asyncio
async def test_get_budget_view_uses_debit_sum(monkeypatch, financial_stub):
    _patch_ext_ids(monkeypatch, ["ext-1"])
    financial_stub.ledgers["ext-1"] = [
        _entry("2025-06-15T09:00:00+00:00", "DEBIT", 5000),
        _entry("2025-06-20T09:00:00+00:00", "CREDIT", 7000),
    ]

    data = await get_budget_view(uuid4(), session=_SESSION)

    assert isinstance(data, BudgetData)
    assert len(data.budgetItems) == 1
    assert data.budgetItems[0].used == 5000
    # 예산 목표/구독 원천이 없어 subItems 는 빈 리스트.
    assert data.subItems == []


@pytest.mark.asyncio
async def test_get_cards_view_is_empty_without_provisioning():
    # 계정계에 계좌별 카드 목록 엔드포인트가 없어 항상 빈 목록(정직한 미프로비저닝).
    data = await get_cards_view(uuid4())
    assert isinstance(data, CardsData)
    assert data.cards == []


# ── 라우터 인증 게이트 ───────────────────────────────────────────────────────


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
