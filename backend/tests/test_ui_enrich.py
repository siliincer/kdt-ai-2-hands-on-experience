"""http 모드 UI enrich(소비/예산/카드) 단위 테스트.

원장 dict -> 뷰 모델 변환 로직(순수 함수)을 DB/네트워크 없이 검증한다.
"""

from uuid import uuid4

import pytest

from backend.services import ui_service
from backend.services.ui_service import _budget_from_ledger, _spending_from_ledger


def _entry(entry_type: str, amount: int, created_at: str) -> dict:
    return {"entry_type": entry_type, "amount": amount, "created_at": created_at}


def test_spending_from_ledger_aggregates_out_only():
    entries = [
        _entry("DEBIT", 30000, "2026-06-05T10:00:00Z"),
        _entry("DEBIT", 20000, "2026-06-20T10:00:00Z"),
        _entry("CREDIT", 1000000, "2026-06-25T10:00:00Z"),  # 입금은 소비 제외
        _entry("DEBIT", 15000, "2026-07-02T10:00:00Z"),
    ]
    data = _spending_from_ledger(entries)

    assert len(data.pie) == 1
    assert data.pie[0].name == "기타"
    assert data.pie[0].amount == 65000
    assert data.bar == []
    assert {m.month: m.amount for m in data.monthly} == {"6월": 50000, "7월": 15000}
    assert set(data.catTx) == {"기타"}
    assert len(data.catTx["기타"]) == 3


def test_spending_empty_when_no_out():
    data = _spending_from_ledger([_entry("CREDIT", 1000, "2026-06-01T00:00:00Z")])
    assert data.pie == []
    assert data.catTx == {}
    assert data.monthly == []


def test_budget_from_ledger_uses_out_total_and_default_total():
    entries = [
        _entry("DEBIT", 30000, "2026-06-05T10:00:00Z"),
        _entry("CREDIT", 5000, "2026-06-06T10:00:00Z"),
        _entry("DEBIT", 20000, "2026-06-07T10:00:00Z"),
    ]
    data = _budget_from_ledger(entries)

    assert len(data.budgetItems) == 1
    item = data.budgetItems[0]
    assert item.cat == "기타"
    assert item.used == 50000
    assert item.total == 1_000_000
    assert data.subItems == []


@pytest.mark.asyncio
async def test_cards_http_returns_empty(monkeypatch):
    monkeypatch.setattr(ui_service.settings, "FINANCIAL_CLIENT", "http")
    data = await ui_service.get_cards_view(uuid4(), None)
    assert data.cards == []


@pytest.mark.asyncio
async def test_cards_mock_returns_fixture():
    data = await ui_service.get_cards_view(uuid4())
    assert len(data.cards) >= 1


@pytest.mark.asyncio
async def test_balance_view_uses_mapped_bank_and_tail(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(ui_service.settings, "FINANCIAL_CLIENT", "http")

    async def rows(session, user_id):
        return [
            SimpleNamespace(
                external_account_id="ext-1",
                bank_name="KDT은행",
                account_number="271-069-693651",
            )
        ]

    class _Client:
        async def get_balance(self, account_id):
            assert account_id == "ext-1"
            return {"account_id": "ext-1", "balance": 500000, "currency": "KRW"}

    monkeypatch.setattr(ui_service, "get_mapped_accounts", rows)
    monkeypatch.setattr(ui_service, "get_financial_client", lambda: _Client())

    data = await ui_service.get_balance_view(uuid4(), None)
    assert data.total == 500000
    # 계정계가 부여한 은행명/계좌번호 tail 사용(기본값 대체 아님).
    assert data.accounts[0].bank == "KDT은행"
    assert data.accounts[0].tail == "3651"
