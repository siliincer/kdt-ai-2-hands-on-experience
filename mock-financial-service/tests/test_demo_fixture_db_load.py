"""Tests for demo_fixtures.load_into_db() — fresh-DB referential integrity.

Loads fixtures produced by get_demo_fixtures() / to_json() into a fresh
in-memory SQLite DB and verifies:
- All three entity tables receive the correct row counts
- Card.account_id FK references real Account rows (DB-level RI)
- card_products is standalone (no FK to cards)
- Category distribution matches spec (4 per category)
"""

from __future__ import annotations

import json
from collections import Counter

import pytest
from financial_service.database import Base
from financial_service.models import Account, Card, CardProduct
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

# ── helpers ───────────────────────────────────────────────────────────────────


@pytest.fixture()
def fresh_engine():
    """Fresh in-memory SQLite engine with FK enforcement enabled."""
    from sqlalchemy import event as sqla_event

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @sqla_event.listens_for(engine, "connect")
    def set_fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def load_result(fresh_engine):
    """Call load_into_db() and return (engine, summary)."""
    from financial_service.demo_fixtures import load_into_db

    summary = load_into_db(fresh_engine)
    return fresh_engine, summary


# ── count assertions ──────────────────────────────────────────────────────────


def test_load_into_db_account_count(load_result):
    _, summary = load_result
    assert summary["accounts"] == 7


def test_load_into_db_card_count_in_range(load_result):
    _, summary = load_result
    assert 5 <= summary["cards"] <= 10


def test_load_into_db_card_product_count(load_result):
    _, summary = load_result
    assert summary["card_products"] == 20


# ── referential integrity via DB ──────────────────────────────────────────────


def test_card_account_fk_integrity_in_db(load_result):
    """Every Card.account_id must reference an existing Account row."""
    engine, _ = load_result
    with Session(engine) as s:
        valid_ids = {a.account_id for a in s.query(Account).all()}
        for card in s.query(Card).all():
            assert card.account_id in valid_ids, f"Card {card.card_id} references unknown account_id {card.account_id}"


def test_cards_per_account_one_or_two_in_db(load_result):
    """Each Account must have 1 or 2 Cards after load."""
    engine, _ = load_result
    with Session(engine) as s:
        accounts = s.query(Account).all()
        for acct in accounts:
            n = s.query(Card).filter(Card.account_id == acct.account_id).count()
            assert 1 <= n <= 2, f"Account {acct.account_id} has {n} cards in DB; expected 1-2"


def test_card_products_no_fk_to_cards_structural(fresh_engine):
    """card_products table must not have a FK pointing to cards table."""
    inspector = inspect(fresh_engine)
    fks = inspector.get_foreign_keys("card_products")
    for fk in fks:
        assert fk.get("referred_table") != "cards", "card_products must not reference the cards table"
    # also must not reference accounts
    for fk in fks:
        assert fk.get("referred_table") != "accounts", "card_products must not reference the accounts table"


def test_card_product_category_distribution_in_db(load_result):
    """Each of 5 categories must have exactly 4 CardProduct rows in DB."""
    engine, _ = load_result
    with Session(engine) as s:
        products = s.query(CardProduct).all()
        cat_counts = Counter(p.category for p in products)

    expected = {"외식", "쇼핑", "여행", "웹구독", "마트/편의점"}
    assert set(cat_counts.keys()) == expected, f"Unexpected categories in DB: {set(cat_counts.keys()) - expected}"
    for cat, n in cat_counts.items():
        assert n == 4, f"Category '{cat}' has {n} rows in DB; expected 4"


# ── JSON round-trip into DB ───────────────────────────────────────────────────


def test_json_fixture_parses_and_counts_match():
    """to_json() output must parse to correct entity counts (no DB needed)."""
    from financial_service.demo_fixtures import to_json

    data = json.loads(to_json())
    assert len(data["accounts"]) == 7
    assert 5 <= len(data["cards"]) <= 10
    assert len(data["card_products"]) == 20


def test_json_fixture_card_account_fk_integrity():
    """JSON output: every card's account_id must exist in accounts list."""
    from financial_service.demo_fixtures import to_json

    data = json.loads(to_json())
    valid_ids = {a["account_id"] for a in data["accounts"]}
    for card in data["cards"]:
        assert card["account_id"] in valid_ids, (
            f"JSON card {card['card_id']} references unknown account_id {card['account_id']}"
        )


def test_json_fixture_card_products_standalone():
    """JSON card_products rows must not contain card_id or account_id."""
    from financial_service.demo_fixtures import to_json

    data = json.loads(to_json())
    for cp in data["card_products"]:
        assert "card_id" not in cp, f"card_product {cp['card_product_id']} must not have card_id"
        assert "account_id" not in cp, f"card_product {cp['card_product_id']} must not have account_id"
