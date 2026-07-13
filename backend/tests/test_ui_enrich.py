"""http 모드 UI enrich(소비/예산/카드) 단위 테스트.

원장 dict -> 뷰 모델 변환 로직(순수 함수)을 DB/네트워크 없이 검증한다.
"""

from uuid import uuid4

import pytest
from fastapi import HTTPException

from backend.services import ui_service
from backend.services.ui_service import (
    _budget_from_ledger,
    _ledger_to_recent,
    _mask_card_number,
    _spending_from_ledger,
)


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


def test_mask_card_number_masks_middle_groups():
    assert _mask_card_number("5412 3456 7890 1234") == "5412 **** **** 1234"


def test_mask_card_number_leaves_short_input():
    # 그룹이 2개 이하면 가릴 중간이 없어 원본 유지.
    assert _mask_card_number("1234 5678") == "1234 5678"


def test_ledger_to_recent_signs_amount_and_maps_type():
    credit = _ledger_to_recent(
        {"entry_type": "CREDIT", "amount": 3000, "created_at": "2026-06-25T09:00:00Z"}
    )
    assert credit.amount == 3000
    assert credit.type == "in"

    debit = _ledger_to_recent(
        {"entry_type": "DEBIT", "amount": 7500, "created_at": "2026-06-28T14:23:00Z"}
    )
    assert debit.amount == -7500  # 출금은 음수 부호
    assert debit.type == "out"


@pytest.mark.asyncio
async def test_cards_http_returns_empty(monkeypatch):
    monkeypatch.setattr(ui_service.settings, "FINANCIAL_CLIENT", "http")
    data = await ui_service.get_cards_view(uuid4(), None)
    assert data.cards == []


@pytest.mark.asyncio
async def test_cards_mock_returns_masked_fixture():
    data = await ui_service.get_cards_view(uuid4())
    assert len(data.cards) >= 1
    # mock 모드에서도 카드번호는 마스킹되어 내려간다(B6 PII 규칙).
    assert all("****" in c.num for c in data.cards)


@pytest.mark.asyncio
async def test_account_detail_mock_returns_fixture():
    data = await ui_service.get_account_detail_view(uuid4(), "acc_001")
    assert data.account.balance > 0
    assert len(data.recent) >= 1


@pytest.mark.asyncio
async def test_account_detail_http_unknown_account_404(monkeypatch):
    monkeypatch.setattr(ui_service.settings, "FINANCIAL_CLIENT", "http")

    async def _no_rows(session, user_id):
        return []

    monkeypatch.setattr(ui_service, "get_mapped_accounts", _no_rows)

    with pytest.raises(HTTPException) as exc:
        await ui_service.get_account_detail_view(uuid4(), "not-mine", None)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_account_detail_http_builds_view(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(ui_service.settings, "FINANCIAL_CLIENT", "http")

    async def _rows(session, user_id):
        return [
            SimpleNamespace(
                external_account_id="ext-1",
                bank_name="KDT은행",
                account_number="271-069-693651",
            )
        ]

    class _Client:
        async def get_balance(self, account_id):
            return {"account_id": "ext-1", "balance": 500000, "currency": "KRW"}

        async def get_ledger(self, account_id, limit=50, offset=0):
            return [
                {
                    "entry_type": "DEBIT",
                    "amount": 7500,
                    "created_at": "2026-06-28T14:23:00Z",
                }
            ]

    monkeypatch.setattr(ui_service, "get_mapped_accounts", _rows)
    monkeypatch.setattr(ui_service, "get_financial_client", lambda: _Client())

    data = await ui_service.get_account_detail_view(uuid4(), "ext-1", None)
    assert data.account.bank == "KDT은행"
    assert data.account.tail == "3651"
    assert data.account.balance == 500000
    assert data.recent[0].amount == -7500


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
