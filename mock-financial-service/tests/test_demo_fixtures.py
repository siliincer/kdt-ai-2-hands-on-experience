"""Tests for financial_service.demo_fixtures module.

Verifies that get_demo_fixtures() and to_json() emit dataset whose shape
matches the Accounts, Cards, and CardProducts schema.
"""

from __future__ import annotations

import json
from collections import Counter

import pytest

# ── fixture ────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def fixtures():
    from financial_service.demo_fixtures import get_demo_fixtures

    return get_demo_fixtures()


# ── top-level structure ────────────────────────────────────────────────────────


def test_top_level_keys_present(fixtures):
    assert set(fixtures.keys()) == {"accounts", "cards", "card_products"}


def test_all_sections_are_lists(fixtures):
    for key in ("accounts", "cards", "card_products"):
        assert isinstance(fixtures[key], list), f"'{key}' must be a list"


# ── accounts shape ─────────────────────────────────────────────────────────────


def test_accounts_count(fixtures):
    assert len(fixtures["accounts"]) == 5


def test_accounts_required_fields(fixtures):
    required = {"account_id", "owner", "currency"}
    for i, row in enumerate(fixtures["accounts"]):
        missing = required - row.keys()
        assert not missing, f"accounts[{i}] missing fields: {missing}"


def test_accounts_field_types(fixtures):
    for i, row in enumerate(fixtures["accounts"]):
        assert isinstance(row["account_id"], str), f"accounts[{i}].account_id must be str"
        assert isinstance(row["owner"], str), f"accounts[{i}].owner must be str"
        assert isinstance(row["currency"], str), f"accounts[{i}].currency must be str"


def test_accounts_unique_ids(fixtures):
    ids = [r["account_id"] for r in fixtures["accounts"]]
    assert len(ids) == len(set(ids)), "Duplicate account_id in accounts"


def test_accounts_nonempty_fields(fixtures):
    for i, row in enumerate(fixtures["accounts"]):
        assert row["owner"].strip(), f"accounts[{i}].owner is empty"
        assert row["currency"].strip(), f"accounts[{i}].currency is empty"


# ── cards shape ────────────────────────────────────────────────────────────────


def test_cards_count_in_range(fixtures):
    n = len(fixtures["cards"])
    assert 5 <= n <= 10, f"Expected 5-10 cards, got {n}"


def test_cards_required_fields(fixtures):
    required = {"card_id", "account_id", "limit", "currency"}
    for i, row in enumerate(fixtures["cards"]):
        missing = required - row.keys()
        assert not missing, f"cards[{i}] missing fields: {missing}"


def test_cards_field_types(fixtures):
    for i, row in enumerate(fixtures["cards"]):
        assert isinstance(row["card_id"], str), f"cards[{i}].card_id must be str"
        assert isinstance(row["account_id"], str), f"cards[{i}].account_id must be str"
        assert isinstance(row["limit"], int), f"cards[{i}].limit must be int"
        assert isinstance(row["currency"], str), f"cards[{i}].currency must be str"


def test_cards_positive_limits(fixtures):
    for i, row in enumerate(fixtures["cards"]):
        assert row["limit"] > 0, f"cards[{i}].limit must be positive"


def test_cards_referential_integrity(fixtures):
    valid_ids = {r["account_id"] for r in fixtures["accounts"]}
    for i, row in enumerate(fixtures["cards"]):
        assert row["account_id"] in valid_ids, f"cards[{i}].account_id '{row['account_id']}' not in accounts"


def test_cards_unique_ids(fixtures):
    ids = [r["card_id"] for r in fixtures["cards"]]
    assert len(ids) == len(set(ids)), "Duplicate card_id in cards"


def test_cards_per_account_one_or_two(fixtures):
    counts = Counter(r["account_id"] for r in fixtures["cards"])
    for acct_id in {r["account_id"] for r in fixtures["accounts"]}:
        n = counts.get(acct_id, 0)
        assert 1 <= n <= 2, f"Account {acct_id} has {n} cards; expected 1-2"


# ── card_products shape ────────────────────────────────────────────────────────


def test_card_products_count(fixtures):
    assert len(fixtures["card_products"]) == 20


def test_card_products_required_fields(fixtures):
    required = {"card_product_id", "product_name", "category", "annual_fee", "benefits"}
    for i, row in enumerate(fixtures["card_products"]):
        missing = required - row.keys()
        assert not missing, f"card_products[{i}] missing fields: {missing}"


def test_card_products_field_types(fixtures):
    for i, row in enumerate(fixtures["card_products"]):
        assert isinstance(row["card_product_id"], str), f"card_products[{i}].card_product_id must be str"
        assert isinstance(row["product_name"], str), f"card_products[{i}].product_name must be str"
        assert isinstance(row["category"], str), f"card_products[{i}].category must be str"
        assert isinstance(row["annual_fee"], int), f"card_products[{i}].annual_fee must be int"
        assert isinstance(row["benefits"], str), f"card_products[{i}].benefits must be str (JSON)"


def test_card_products_unique_ids(fixtures):
    ids = [r["card_product_id"] for r in fixtures["card_products"]]
    assert len(ids) == len(set(ids)), "Duplicate card_product_id in card_products"


def test_card_products_allowed_categories(fixtures):
    allowed = {"외식", "쇼핑", "여행", "웹구독", "마트/편의점"}
    found = {r["category"] for r in fixtures["card_products"]}
    assert found == allowed, f"Unexpected categories: {found - allowed}"


def test_card_products_four_per_category(fixtures):
    counts = Counter(r["category"] for r in fixtures["card_products"])
    for cat, n in counts.items():
        assert n == 4, f"Category '{cat}' has {n} products; expected 4"


def test_card_products_benefits_valid_json_list(fixtures):
    for i, row in enumerate(fixtures["card_products"]):
        parsed = json.loads(row["benefits"])
        assert isinstance(parsed, list), f"card_products[{i}].benefits must be JSON list"
        assert len(parsed) >= 1, f"card_products[{i}].benefits must be non-empty"


def test_card_products_annual_fee_nonnegative(fixtures):
    for i, row in enumerate(fixtures["card_products"]):
        assert row["annual_fee"] >= 0, f"card_products[{i}].annual_fee must be >= 0"


def test_card_products_no_fk_fields(fixtures):
    """card_products is standalone — rows must not carry card_id or account_id."""
    for i, row in enumerate(fixtures["card_products"]):
        assert "card_id" not in row, f"card_products[{i}] must not have card_id"
        assert "account_id" not in row, f"card_products[{i}] must not have account_id"


# ── to_json serialisation ──────────────────────────────────────────────────────


def test_to_json_returns_string():
    from financial_service.demo_fixtures import to_json

    result = to_json()
    assert isinstance(result, str)


def test_to_json_parses_to_correct_structure():
    from financial_service.demo_fixtures import to_json

    parsed = json.loads(to_json())
    assert set(parsed.keys()) == {"accounts", "cards", "card_products"}
    assert len(parsed["accounts"]) == 5
    assert 5 <= len(parsed["cards"]) <= 10
    assert len(parsed["card_products"]) == 20


def test_to_json_indent_default():
    from financial_service.demo_fixtures import to_json

    result = to_json()
    # Default indent=2 means newlines are present
    assert "\n" in result


def test_to_json_roundtrip_consistency():
    """get_demo_fixtures() dict and to_json() parsed must be identical."""
    from financial_service.demo_fixtures import get_demo_fixtures, to_json

    direct = get_demo_fixtures()
    via_json = json.loads(to_json())
    assert direct == via_json
