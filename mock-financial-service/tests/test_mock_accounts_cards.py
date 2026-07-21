"""Tests: mock Accounts and Cards dataset.

Verifies:
  1. Exactly 5 Accounts seeded
  2. 5-10 Cards seeded (8 total)
  3. Each Account has 1-2 Cards
  4. Every Card.account_id FK references a real Account
"""

import pytest
from financial_service.mock_data import (
    MOCK_ACCOUNTS,
    MOCK_CARDS,
    make_account_rows,
    make_card_rows,
)
from financial_service.models import Account, Card
from sqlalchemy.orm import Session


@pytest.fixture()
def seeded_session(db_engine):
    """In-memory DB seeded with mock Accounts and Cards."""
    with Session(db_engine) as session:
        session.add_all(make_account_rows())
        session.flush()
        session.add_all(make_card_rows())
        session.commit()
        yield session


# ── 1. Account count ──────────────────────────────────────────────────────────


def test_mock_account_count(seeded_session):
    count = seeded_session.query(Account).count()
    assert count == 5, f"Expected 5 Accounts, got {count}"


# ── 2. Card total count ───────────────────────────────────────────────────────


def test_mock_card_count_in_range(seeded_session):
    count = seeded_session.query(Card).count()
    assert 5 <= count <= 10, f"Expected 5-10 Cards, got {count}"


def test_mock_card_count_exact(seeded_session):
    """Exact fixture count: 8 cards."""
    count = seeded_session.query(Card).count()
    assert count == 8, f"Expected 8 Cards, got {count}"


# ── 3. Cards per Account: 1-2 each ───────────────────────────────────────────


def test_each_account_has_one_or_two_cards(seeded_session):
    accounts = seeded_session.query(Account).all()
    for acct in accounts:
        n = seeded_session.query(Card).filter(Card.account_id == acct.account_id).count()
        assert 1 <= n <= 2, f"Account {acct.account_id} ({acct.owner}) has {n} cards; expected 1-2"


# ── 4. FK integrity: every Card.account_id points to a real Account ───────────


def test_all_card_account_ids_are_valid(seeded_session):
    valid_ids = {a.account_id for a in seeded_session.query(Account).all()}
    cards = seeded_session.query(Card).all()
    for card in cards:
        assert card.account_id in valid_ids, f"Card {card.card_id} references unknown account_id {card.account_id}"


# ── 5. Data-layer sanity: MOCK_* constants match ORM rows ─────────────────────


def test_mock_constants_match_db_rows(seeded_session):
    """Fixture dicts and DB rows are consistent."""
    assert len(MOCK_ACCOUNTS) == 5
    assert 5 <= len(MOCK_CARDS) <= 10

    db_account_ids = {a.account_id for a in seeded_session.query(Account).all()}
    for d in MOCK_ACCOUNTS:
        assert d["account_id"] in db_account_ids

    db_card_ids = {c.card_id for c in seeded_session.query(Card).all()}
    for d in MOCK_CARDS:
        assert d["card_id"] in db_card_ids
