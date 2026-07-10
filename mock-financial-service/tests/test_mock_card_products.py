"""Tests for mock CardProduct catalog data.

Verifies:
1. MOCK_CARD_PRODUCTS list has exactly 20 entries
2. Exactly 4 entries per each of 5 categories
3. Category values restricted to the 5 allowed
4. Each row has required fields: card_product_id, product_name, category, annual_fee, benefits
5. benefits is valid JSON-encoded list with at least 1 item
6. annual_fee is non-negative integer
7. ORM instances insertable into in-memory SQLite (integration)
8. card_products table has no FK to cards table
"""

from __future__ import annotations

import json
from collections import Counter

import pytest
from financial_service.mock_data import (
    CARD_PRODUCT_CATEGORIES,
    MOCK_CARD_PRODUCTS,
    make_card_product_rows,
)
from financial_service.models import CardProduct
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from financial_service.database import Base

EXPECTED_CATEGORIES = set(CARD_PRODUCT_CATEGORIES)
EXPECTED_TOTAL = 20
EXPECTED_PER_CATEGORY = 4


# ── unit-level dict checks ─────────────────────────────────────────────────────


def test_total_count():
    assert len(MOCK_CARD_PRODUCTS) == EXPECTED_TOTAL


def test_four_per_category():
    counts = Counter(row["category"] for row in MOCK_CARD_PRODUCTS)
    for cat in EXPECTED_CATEGORIES:
        assert counts[cat] == EXPECTED_PER_CATEGORY, (
            f"category '{cat}' has {counts[cat]} rows, expected {EXPECTED_PER_CATEGORY}"
        )


def test_no_unexpected_categories():
    categories_found = {row["category"] for row in MOCK_CARD_PRODUCTS}
    assert categories_found == EXPECTED_CATEGORIES


def test_required_fields_present():
    required = {"card_product_id", "product_name", "category", "annual_fee", "benefits"}
    for i, row in enumerate(MOCK_CARD_PRODUCTS):
        missing = required - row.keys()
        assert not missing, f"Row {i} missing fields: {missing}"


def test_benefits_valid_json_list():
    for i, row in enumerate(MOCK_CARD_PRODUCTS):
        parsed = json.loads(row["benefits"])
        assert isinstance(parsed, list), f"Row {i} benefits not a list"
        assert len(parsed) >= 1, f"Row {i} benefits list is empty"


def test_annual_fee_non_negative():
    for i, row in enumerate(MOCK_CARD_PRODUCTS):
        assert row["annual_fee"] >= 0, f"Row {i} annual_fee is negative: {row['annual_fee']}"


def test_unique_card_product_ids():
    ids = [row["card_product_id"] for row in MOCK_CARD_PRODUCTS]
    assert len(ids) == len(set(ids)), "Duplicate card_product_id found"


def test_unique_product_names():
    names = [row["product_name"] for row in MOCK_CARD_PRODUCTS]
    assert len(names) == len(set(names)), "Duplicate product_name found"


# ── ORM factory check ─────────────────────────────────────────────────────────


def test_make_card_product_rows_returns_orm_instances():
    rows = make_card_product_rows()
    assert len(rows) == EXPECTED_TOTAL
    assert all(isinstance(r, CardProduct) for r in rows)


# ── integration: insert into in-memory SQLite ─────────────────────────────────


@pytest.fixture(scope="module")
def mem_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="module")
def session(mem_engine):
    Session = sessionmaker(bind=mem_engine, autocommit=False, autoflush=False)
    s = Session()
    s.add_all(make_card_product_rows())
    s.commit()
    yield s
    s.close()


def test_db_total_count(session):
    count = session.query(CardProduct).count()
    assert count == EXPECTED_TOTAL


def test_db_four_per_category(session):
    for cat in EXPECTED_CATEGORIES:
        count = session.query(CardProduct).filter(CardProduct.category == cat).count()
        assert count == EXPECTED_PER_CATEGORY, (
            f"DB: category '{cat}' has {count} rows, expected {EXPECTED_PER_CATEGORY}"
        )


def test_card_products_table_has_no_fk_to_cards(mem_engine):
    """card_products must be standalone — no FK referencing cards table."""
    inspector = inspect(mem_engine)
    fks = inspector.get_foreign_keys("card_products")
    for fk in fks:
        assert fk.get("referred_table") != "cards", (
            "card_products has unexpected FK to cards table"
        )
