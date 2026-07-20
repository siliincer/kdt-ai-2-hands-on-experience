"""거래 상호명/카테고리 테스트 (카드결제 전용 — CardLedgerEntry).

카테고리는 카드결제 단위(CardLedgerEntry)에만 붙는다. 계좌이체의 "상호명"은
기존 LedgerEntryResponse.counterparty_owner로 이미 충족되며 여기서 다루지 않는다.
"""

from __future__ import annotations

from financial_service.merchant_catalog import (
    MERCHANT_CATEGORY,
    MERCHANTS_BY_CATEGORY,
    category_for_merchant,
)
from financial_service.mock_data import MOCK_CARD_LEDGER_ENTRIES


def test_category_for_known_merchant():
    assert category_for_merchant("스타벅스") == "외식"
    assert category_for_merchant("이마트") == "마트/편의점"


def test_category_for_unknown_merchant_is_none():
    assert category_for_merchant("존재하지않는가게") is None


def test_category_for_none_is_none():
    assert category_for_merchant(None) is None


def test_merchant_category_reverse_index_matches_catalog():
    for category, merchants in MERCHANTS_BY_CATEGORY.items():
        for merchant in merchants:
            assert MERCHANT_CATEGORY[merchant] == category


def test_mock_card_ledger_entries_all_have_category():
    """시드 카드 이벤트는 카탈로그 안의 상호명만 쓰므로 category가 빠짐없이 채워진다."""
    assert MOCK_CARD_LEDGER_ENTRIES, "mock dataset must be non-empty"
    for entry in MOCK_CARD_LEDGER_ENTRIES:
        assert entry["merchant_name"] is not None
        assert entry["category"] is not None
        assert entry["category"] == category_for_merchant(entry["merchant_name"])
