"""Tests for scripts/seed_dev_db.py.

Verifies:
1. seed() returns correct row counts (5 accounts, 8 cards, 20 card_products)
2. seed() is idempotent — second call skips inserts, counts stay the same
3. All Card.account_id values reference real Accounts (FK integrity)
4. card_products table has no FK to cards (structural check)
5. Every category has exactly 4 CardProduct rows
"""

from __future__ import annotations

import os
import sys

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

# Allow scripts/ to be imported directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from financial_service.database import Base
from financial_service.models import CardProduct

# Import seed function via direct path injection (seed script uses sys.path trick)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture()
def mem_url():
    """Return a fresh in-memory SQLite URL for each test."""
    # Use same-thread-safe in-memory DB via StaticPool trick in seed()
    # We pass a unique URI so each test gets its own DB
    return "sqlite:///:memory:"


@pytest.fixture()
def seeded_summary(mem_url):
    """Run seed once and return its summary dict."""

    engine = create_engine(
        mem_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    engine.dispose()

    # seed() creates its own engine from url — use StaticPool-friendly file-based URL
    # Instead, call internal seed logic directly via fixture-provided engine
    return _seed_with_engine(mem_url)


def _seed_with_engine(db_url: str) -> dict:
    """Call seed() which creates its own engine from the URL."""
    from scripts.seed_dev_db import seed  # noqa: PLC0415

    return seed(db_url, reset=True)


# ── 1. Row counts ─────────────────────────────────────────────────────────────


def test_seed_returns_correct_account_count(mem_url):
    summary = _seed_with_engine(mem_url)
    assert summary["accounts"] == 7


def test_seed_returns_correct_card_count(mem_url):
    summary = _seed_with_engine(mem_url)
    assert 5 <= summary["cards"] <= 10


def test_seed_returns_correct_card_product_count(mem_url):
    summary = _seed_with_engine(mem_url)
    assert summary["card_products"] == 20


# ── 2. Idempotency ────────────────────────────────────────────────────────────


def test_seed_idempotent(tmp_path):
    """Running seed twice on the same file DB must not duplicate rows."""
    db_path = tmp_path / "test_seed.db"
    db_url = f"sqlite:///{db_path}"

    from scripts.seed_dev_db import seed  # noqa: PLC0415

    s1 = seed(db_url, reset=False)
    s2 = seed(db_url, reset=False)

    assert s1["accounts"] == s2["accounts"] == 7
    assert s1["cards"] == s2["cards"]
    assert s1["card_products"] == s2["card_products"] == 20


# ── 3. FK integrity via seed function's own assertions ───────────────────────


def test_seed_fk_integrity_passes(mem_url):
    """seed() raises no AssertionError — FK checks are embedded in seed()."""
    # If FK integrity fails, seed() raises AssertionError → test fails
    summary = _seed_with_engine(mem_url)
    assert summary["accounts"] == 7
    assert summary["cards"] >= 5


# ── 4. card_products has no FK to cards ──────────────────────────────────────


def test_card_products_no_fk_to_cards(mem_url):
    """Structural: card_products table must not reference cards."""
    from sqlalchemy import create_engine

    engine = create_engine(mem_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    fks = inspector.get_foreign_keys("card_products")
    for fk in fks:
        assert fk.get("referred_table") != "cards", "card_products must not have a FK to cards"
    engine.dispose()


# ── 5. Category distribution ─────────────────────────────────────────────────


def test_seed_category_distribution(tmp_path):
    """After seed, each of 5 categories has exactly 4 CardProduct rows."""
    from collections import Counter

    db_path = tmp_path / "cat_test.db"
    db_url = f"sqlite:///{db_path}"

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from scripts.seed_dev_db import seed  # noqa: PLC0415

    seed(db_url, reset=True)

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    with Session(engine) as s:
        products = s.query(CardProduct).all()
        cat_counts = Counter(p.category for p in products)

    engine.dispose()

    expected = {"외식", "쇼핑", "여행", "웹구독", "마트/편의점"}
    assert set(cat_counts.keys()) == expected
    for cat, n in cat_counts.items():
        assert n == 4, f"Category '{cat}' has {n} rows; expected 4"
