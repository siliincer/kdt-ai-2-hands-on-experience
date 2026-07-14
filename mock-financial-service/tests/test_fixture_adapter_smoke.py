"""Smoke test: conftest.py fixture adapter for canonical mock dataset.

Verifies that accounts/cards/card_products fixtures:
- Inject correct collection types and counts
- Expose required fields on each item
- Maintain referential integrity (card.account_id → account)
- card_products has no card_id / account_id FK fields
"""

from __future__ import annotations

import json

# ── accounts fixture ──────────────────────────────────────────────────────────


def test_accounts_fixture_count(accounts):
    assert len(accounts) == 5, f"Expected 5 accounts, got {len(accounts)}"


def test_accounts_fixture_required_fields(accounts):
    required = {"account_id", "owner", "currency"}
    for i, acct in enumerate(accounts):
        missing = required - acct.keys()
        assert not missing, f"accounts[{i}] missing fields: {missing}"


def test_accounts_fixture_unique_ids(accounts):
    ids = [a["account_id"] for a in accounts]
    assert len(ids) == len(set(ids)), "Duplicate account_id in accounts fixture"


# ── cards fixture ─────────────────────────────────────────────────────────────


def test_cards_fixture_count_in_range(cards):
    n = len(cards)
    assert 5 <= n <= 10, f"Expected 5-10 cards, got {n}"


def test_cards_fixture_required_fields(cards):
    required = {"card_id", "account_id", "limit", "currency"}
    for i, card in enumerate(cards):
        missing = required - card.keys()
        assert not missing, f"cards[{i}] missing fields: {missing}"


def test_cards_fixture_fk_integrity(accounts, cards):
    valid_ids = {a["account_id"] for a in accounts}
    for card in cards:
        assert card["account_id"] in valid_ids, (
            f"Card {card['card_id']} references unknown account_id {card['account_id']}"
        )


def test_cards_fixture_positive_limits(cards):
    for card in cards:
        assert card["limit"] > 0, f"Card {card['card_id']} has non-positive limit"


# ── card_products fixture ─────────────────────────────────────────────────────


def test_card_products_fixture_count(card_products):
    assert len(card_products) == 20, (
        f"Expected 20 card_products, got {len(card_products)}"
    )


def test_card_products_fixture_required_fields(card_products):
    required = {"card_product_id", "product_name", "category", "annual_fee", "benefits"}
    for i, cp in enumerate(card_products):
        missing = required - cp.keys()
        assert not missing, f"card_products[{i}] missing fields: {missing}"


def test_card_products_fixture_no_fk_fields(card_products):
    """card_products is standalone — must not contain card_id or account_id."""
    for cp in card_products:
        assert "card_id" not in cp, (
            f"CardProduct {cp['card_product_id']} must not have card_id"
        )
        assert "account_id" not in cp, (
            f"CardProduct {cp['card_product_id']} must not have account_id"
        )


def test_card_products_fixture_categories(card_products):
    allowed = {"외식", "쇼핑", "여행", "웹구독", "마트/편의점"}
    found = {cp["category"] for cp in card_products}
    assert found == allowed, f"Unexpected categories: {found - allowed}"


def test_card_products_fixture_four_per_category(card_products):
    from collections import Counter

    counts = Counter(cp["category"] for cp in card_products)
    for cat, n in counts.items():
        assert n == 4, f"Category '{cat}' has {n} products; expected 4"


def test_card_products_fixture_benefits_valid_json(card_products):
    for i, cp in enumerate(card_products):
        parsed = json.loads(cp["benefits"])
        assert isinstance(parsed, list) and len(parsed) >= 1, (
            f"card_products[{i}] benefits must be non-empty JSON array"
        )
