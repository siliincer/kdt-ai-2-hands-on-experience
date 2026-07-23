"""Demo fixture module.

Emits the canonical mock dataset (Accounts, Cards, CardProducts) as
structured demo fixtures in dict or JSON form.

The returned structure is intentionally format-agnostic so callers can
serialise it to JSON, YAML, or use it directly in tests / documentation.

Public API
----------
get_demo_fixtures() -> dict
    Return the full dataset keyed by entity type.

to_json(indent=2) -> str
    Serialise get_demo_fixtures() as a JSON string.
"""

from __future__ import annotations

import json

from .mock_data import MOCK_ACCOUNTS, MOCK_CARD_PRODUCTS, MOCK_CARDS

# Field schema: each key maps to its expected Python type.
ACCOUNT_SCHEMA: dict[str, type] = {
    "account_id": str,
    "owner": str,
    "currency": str,
}

CARD_SCHEMA: dict[str, type] = {
    "card_id": str,
    "account_id": str,
    "limit": int,
    "currency": str,
}

CARD_PRODUCT_SCHEMA: dict[str, type] = {
    "card_product_id": str,
    "product_name": str,
    "category": str,
    "annual_fee": int,
    "benefits": str,  # JSON-encoded list
}


def get_demo_fixtures() -> dict:
    """Return the canonical mock dataset as a structured dict.

    Structure::

        {
            "accounts": [
                {"account_id": ..., "owner": ..., "currency": ...},
                ...   # 5 rows
            ],
            "cards": [
                {"card_id": ..., "account_id": ..., "limit": ..., "currency": ...},
                ...   # 5-10 rows, FK to accounts
            ],
            "card_products": [
                {
                    "card_product_id": ..., "product_name": ..., "category": ...,
                    "annual_fee": ..., "benefits": "<json-list-str>",
                },
                ...   # 20 rows, standalone (no FK to cards)
            ],
        }

    Each row is a plain ``dict`` — safe to serialise to JSON/YAML or pass to
    ORM constructors (``Account(**row)``, etc.).
    """
    return {
        "accounts": [dict(r) for r in MOCK_ACCOUNTS],
        "cards": [dict(r) for r in MOCK_CARDS],
        "card_products": [dict(r) for r in MOCK_CARD_PRODUCTS],
    }


def to_json(indent: int = 2) -> str:
    """Return the demo fixtures serialised as a JSON string."""
    return json.dumps(get_demo_fixtures(), ensure_ascii=False, indent=indent)


def load_into_db(engine) -> dict:
    """Load demo fixtures into *engine* and verify referential integrity.

    Inserts Accounts, Cards (FK-safe order), and CardProducts into the DB
    using the ORM models.  Tables must already exist (call
    ``Base.metadata.create_all(bind=engine)`` before calling this function).

    Args:
        engine: SQLAlchemy engine with tables already created.

    Returns:
        dict with keys ``accounts``, ``cards``, ``card_products`` containing
        the post-insert row counts.

    Raises:
        AssertionError: if post-insert counts or referential integrity checks fail.
    """
    from collections import Counter

    from sqlalchemy.orm import Session

    from .mock_data import (
        make_account_rows,
        make_card_product_rows,
        make_card_rows,
    )
    from .models import Account, Card, CardProduct

    with Session(engine) as session:
        session.add_all(make_account_rows())
        session.flush()
        session.add_all(make_card_rows())
        session.add_all(make_card_product_rows())
        session.commit()

        # ── Post-load verification ─────────────────────────────────────────
        n_accounts = session.query(Account).count()
        n_cards = session.query(Card).count()
        n_products = session.query(CardProduct).count()

        assert n_accounts == 7, f"Expected 7 Accounts after load, got {n_accounts}"
        assert 5 <= n_cards <= 10, f"Expected 5-10 Cards after load, got {n_cards}"
        assert n_products == 20, f"Expected 20 CardProducts after load, got {n_products}"

        # Cards per account: 1-2 each
        accounts = session.query(Account).all()
        for acct in accounts:
            n = session.query(Card).filter(Card.account_id == acct.account_id).count()
            assert 1 <= n <= 2, f"Account {acct.account_id} has {n} cards; expected 1-2"

        # FK integrity: every Card.account_id references a real Account
        valid_ids = {a.account_id for a in accounts}
        cards = session.query(Card).all()
        for card in cards:
            assert card.account_id in valid_ids, f"Card {card.card_id} references unknown account_id {card.account_id}"

        # CardProduct category distribution: 4 per each of 5 categories
        products = session.query(CardProduct).all()
        cat_counts = Counter(p.category for p in products)
        expected_cats = {"외식", "쇼핑", "여행", "웹구독", "마트/편의점"}
        for cat in expected_cats:
            assert cat_counts[cat] == 4, f"Category '{cat}' has {cat_counts[cat]} products; expected 4"

        # card_products must not reference cards (structural: no FK columns)
        for cp in products:
            assert not hasattr(cp, "card_id") or cp.__class__.__table__.c.keys().count("card_id") == 0, (
                "CardProduct must not have a card_id FK column"
            )

    return {"accounts": n_accounts, "cards": n_cards, "card_products": n_products}
