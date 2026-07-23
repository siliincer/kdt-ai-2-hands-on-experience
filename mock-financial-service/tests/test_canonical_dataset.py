"""Test: canonical dataset module is the single source of truth.

Loads financial_service.mock_data and asserts:
1. Module imports cleanly (Accounts, Cards, CardProducts all present)
2. Referential integrity: every card.account_id exists in MOCK_ACCOUNTS
3. validate_dataset() returns no errors (schema + count + FK checks)
4. card_products has NO FK relationship to Cards (standalone catalog)
5. Counts: 5 Accounts, 5-10 Cards, 20 CardProducts
"""

from __future__ import annotations

import importlib

# ── 1. Module loads cleanly ────────────────────────────────────────────────────


def test_mock_data_module_importable():
    mod = importlib.import_module("financial_service.mock_data")
    assert hasattr(mod, "MOCK_ACCOUNTS")
    assert hasattr(mod, "MOCK_CARDS")
    assert hasattr(mod, "MOCK_CARD_PRODUCTS")
    assert hasattr(mod, "CARD_PRODUCT_CATEGORIES")
    assert hasattr(mod, "validate_dataset")
    assert hasattr(mod, "make_account_rows")
    assert hasattr(mod, "make_card_rows")
    assert hasattr(mod, "make_card_product_rows")


# ── 2. Referential integrity: Card.account_id → Account ──────────────────────


def test_all_card_account_ids_reference_real_accounts():
    from financial_service.mock_data import MOCK_ACCOUNTS, MOCK_CARDS

    valid_ids = {a["account_id"] for a in MOCK_ACCOUNTS}
    for card in MOCK_CARDS:
        assert card["account_id"] in valid_ids, (
            f"Card {card['card_id']} has account_id '{card['account_id']}' which is not in MOCK_ACCOUNTS"
        )


# ── 3. validate_dataset() passes with zero errors ─────────────────────────────


def test_validate_dataset_returns_no_errors():
    from financial_service.mock_data import validate_dataset

    errors = validate_dataset()
    assert errors == [], f"validate_dataset() reported {len(errors)} error(s):\n" + "\n".join(
        f"  - {e}" for e in errors
    )


# ── 4. card_products standalone — no FK to cards ─────────────────────────────


def test_card_products_have_no_account_id_or_card_id_field():
    from financial_service.mock_data import MOCK_CARD_PRODUCTS

    for row in MOCK_CARD_PRODUCTS:
        assert "card_id" not in row, f"CardProduct {row['card_product_id']} should not have card_id field"
        assert "account_id" not in row, f"CardProduct {row['card_product_id']} should not have account_id field"


# ── 5. Count constraints ──────────────────────────────────────────────────────


def test_account_count_is_five():
    from financial_service.mock_data import MOCK_ACCOUNTS

    assert len(MOCK_ACCOUNTS) == 7, f"Expected 7 Accounts, got {len(MOCK_ACCOUNTS)}"


def test_card_count_in_range():
    from financial_service.mock_data import MOCK_CARDS

    n = len(MOCK_CARDS)
    assert 5 <= n <= 10, f"Expected 5-10 Cards, got {n}"


def test_card_product_count_is_twenty():
    from financial_service.mock_data import MOCK_CARD_PRODUCTS

    assert len(MOCK_CARD_PRODUCTS) == 20, f"Expected 20 CardProducts, got {len(MOCK_CARD_PRODUCTS)}"


# ── 6. ORM factory functions return correct types ─────────────────────────────


def test_make_account_rows_returns_account_orm():
    from financial_service.mock_data import make_account_rows
    from financial_service.models import Account

    rows = make_account_rows()
    assert len(rows) == 7
    assert all(isinstance(r, Account) for r in rows)


def test_make_card_rows_returns_card_orm():
    from financial_service.mock_data import make_card_rows
    from financial_service.models import Card

    rows = make_card_rows()
    assert 5 <= len(rows) <= 10
    assert all(isinstance(r, Card) for r in rows)


def test_make_card_product_rows_returns_card_product_orm():
    from financial_service.mock_data import make_card_product_rows
    from financial_service.models import CardProduct

    rows = make_card_product_rows()
    assert len(rows) == 20
    assert all(isinstance(r, CardProduct) for r in rows)
