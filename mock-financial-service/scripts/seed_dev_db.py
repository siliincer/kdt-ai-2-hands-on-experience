#!/usr/bin/env python
"""Dev DB seed script — inserts canonical mock data (Accounts, Cards, CardProducts).

Usage:
    python scripts/seed_dev_db.py               # seeds financial.db in CWD
    python scripts/seed_dev_db.py sqlite:///./other.db
    python scripts/seed_dev_db.py --reset       # DROP + recreate tables first

Exit codes:
    0  seed successful
    1  seed failed (row counts or FK mismatch)
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter

sys.path.insert(0, "src")

from financial_service.database import Base
from financial_service.mock_data import (
    MOCK_CARD_LEDGER_ENTRIES,
    MOCK_LEDGER_ENTRIES,
    MOCK_TRANSACTIONS,
    make_account_rows,
    make_biller_account_rows,
    make_card_ledger_entry_rows,
    make_card_product_rows,
    make_card_rows,
    make_external_source_account_rows,
    make_ledger_entry_rows,
    make_transaction_rows,
    validate_dataset,
)
from financial_service.models import (
    Account,
    Card,
    CardLedgerEntry,
    CardProduct,
    LedgerEntry,
    Transaction,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

_DEFAULT_URL = "sqlite:///./financial.db"


def seed(db_url: str = _DEFAULT_URL, *, reset: bool = False) -> dict:
    """Seed dev DB. Returns summary dict with row counts.

    Args:
        db_url: SQLAlchemy DB URL. Defaults to SQLite financial.db.
        reset:  If True, drop all tables before recreating (idempotent).

    Returns:
        dict with keys: accounts, cards, card_products (row counts after seed).

    Raises:
        AssertionError: if post-seed counts or FK checks fail.
    """
    engine = create_engine(db_url, connect_args={"check_same_thread": False})

    # Enable FK enforcement for SQLite
    from sqlalchemy import event as _sqla_event

    @_sqla_event.listens_for(engine, "connect")
    def _set_fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    if reset:
        Base.metadata.drop_all(bind=engine)

    Base.metadata.create_all(bind=engine)

    # Pre-flight: validate dataset structure
    errors = validate_dataset()
    if errors:
        for e in errors:
            print(f"[seed] DATA ERROR: {e}", file=sys.stderr)
        raise ValueError(f"Dataset validation failed with {len(errors)} error(s)")

    with Session(engine) as session:
        # Skip seed if data already present (idempotent)
        existing_accounts = session.query(Account).count()
        if existing_accounts > 0:
            print(
                f"[seed] DB already seeded ({existing_accounts} accounts found). "
                "Skipping insert.",
                file=sys.stderr,
            )
        else:
            # Insert in FK-safe order:
            # 1) Accounts (user + biller + external-source) — everything else FKs here
            # 2) Cards (FK → Account) / CardProducts (standalone)
            # 3) Transactions (FK → sender/receiver Account)
            # 4) LedgerEntry (FK → Transaction, Account) / CardLedgerEntry (FK → Card)
            session.add_all(make_account_rows())
            session.add_all(make_biller_account_rows())
            session.add_all(make_external_source_account_rows())
            session.flush()
            session.add_all(make_card_rows())
            session.add_all(make_card_product_rows())
            session.flush()
            session.add_all(make_transaction_rows())
            session.flush()
            session.add_all(make_ledger_entry_rows())
            session.add_all(make_card_ledger_entry_rows())
            session.commit()
            print(
                "[seed] Inserted: 5 Accounts, 7 Biller Accounts, "
                "1 External-source Account, 8 Cards, 20 CardProducts, "
                f"{len(MOCK_TRANSACTIONS)} Transactions, "
                f"{len(MOCK_LEDGER_ENTRIES)} LedgerEntries, "
                f"{len(MOCK_CARD_LEDGER_ENTRIES)} CardLedgerEntries"
            )

        # ── Post-seed verification ─────────────────────────────────────────────
        # Account table holds 3 kinds of rows (no discriminator column):
        # user accounts (acct-000*), biller accounts (acct-b00*), and one
        # external-source account (acct-b099, payroll/peer-transfer origin).
        accounts = session.query(Account).all()
        user_accounts = [a for a in accounts if a.account_id.startswith("acct-000")]
        n_accounts = len(user_accounts)
        n_cards = session.query(Card).count()
        n_products = session.query(CardProduct).count()

        # Count checks
        assert n_accounts == 5, f"Expected 5 user Accounts, got {n_accounts}"
        assert len(accounts) == 5 + 7 + 1, (
            "Expected 13 total Accounts (5 user + 7 biller + 1 external-source), "
            f"got {len(accounts)}"
        )
        assert 5 <= n_cards <= 10, f"Expected 5-10 Cards, got {n_cards}"
        assert n_products == 20, f"Expected 20 CardProducts, got {n_products}"

        # Cards-per-user-account: 1-2 each (billers/external-source own no cards)
        for acct in user_accounts:
            n = session.query(Card).filter(Card.account_id == acct.account_id).count()
            assert 1 <= n <= 2, f"Account {acct.account_id} has {n} cards; expected 1-2"

        # FK integrity: every Card.account_id references a real Account
        valid_ids = {a.account_id for a in accounts}
        cards = session.query(Card).all()
        for card in cards:
            assert card.account_id in valid_ids, (
                f"Card {card.card_id} references unknown account_id {card.account_id}"
            )

        # CardProduct category distribution: 4 per each of 5 categories
        products = session.query(CardProduct).all()
        cat_counts = Counter(p.category for p in products)
        expected_cats = {"외식", "쇼핑", "여행", "웹구독", "마트/편의점"}
        for cat in expected_cats:
            assert cat_counts[cat] == 4, (
                f"Category '{cat}' has {cat_counts[cat]} products; expected 4"
            )

        # card_products has no FK to cards (verified structurally via mock_data)
        # (enforced by model design; no card_id column on CardProduct)

        # ── Transaction / LedgerEntry / CardLedgerEntry verification ──────────
        n_transactions = session.query(Transaction).count()
        n_ledger_entries = session.query(LedgerEntry).count()
        n_card_ledger_entries = session.query(CardLedgerEntry).count()

        assert n_transactions == len(MOCK_TRANSACTIONS), (
            f"Expected {len(MOCK_TRANSACTIONS)} Transactions, got {n_transactions}"
        )
        assert n_ledger_entries == len(MOCK_LEDGER_ENTRIES), (
            f"Expected {len(MOCK_LEDGER_ENTRIES)} LedgerEntries, got {n_ledger_entries}"
        )
        assert n_card_ledger_entries == len(MOCK_CARD_LEDGER_ENTRIES), (
            f"Expected {len(MOCK_CARD_LEDGER_ENTRIES)} CardLedgerEntries, "
            f"got {n_card_ledger_entries}"
        )

        # Double-entry: every success Transaction has exactly one DEBIT + one CREDIT
        # LedgerEntry with matching amount; failure Transactions have none.
        all_transactions = session.query(Transaction).all()
        entries_by_txn: dict[str, list] = {}
        for entry in session.query(LedgerEntry).all():
            entries_by_txn.setdefault(entry.transaction_id, []).append(entry)

        for txn in all_transactions:
            pair = entries_by_txn.get(txn.transaction_id, [])
            if txn.status == "failure":
                assert not pair, (
                    f"Transaction {txn.transaction_id} is a failure "
                    "but has ledger entries"
                )
                continue
            assert len(pair) == 2, (
                f"Transaction {txn.transaction_id} expected 2 ledger entries, "
                f"got {len(pair)}"
            )
            debit = [e for e in pair if e.entry_type == "DEBIT"]
            credit = [e for e in pair if e.entry_type == "CREDIT"]
            assert len(debit) == 1 and len(credit) == 1, (
                f"Transaction {txn.transaction_id} must have exactly "
                "one DEBIT and one CREDIT"
            )
            assert debit[0].amount == credit[0].amount == txn.amount, (
                f"Transaction {txn.transaction_id} DEBIT/CREDIT/amount mismatch"
            )

        # FK integrity: every CardLedgerEntry.card_id references a real Card
        valid_card_ids = {c.card_id for c in cards}
        for entry in session.query(CardLedgerEntry).all():
            assert entry.card_id in valid_card_ids, (
                f"CardLedgerEntry {entry.card_ledger_entry_id} references "
                f"unknown card_id {entry.card_id}"
            )

        summary = {
            "accounts": n_accounts,
            "cards": n_cards,
            "card_products": n_products,
            "transactions": n_transactions,
            "ledger_entries": n_ledger_entries,
            "card_ledger_entries": n_card_ledger_entries,
        }

    engine.dispose()
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed dev DB with canonical mock data."
    )
    parser.add_argument(
        "db_url",
        nargs="?",
        default=_DEFAULT_URL,
        help=f"SQLAlchemy DB URL (default: {_DEFAULT_URL})",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop and recreate all tables before seeding",
    )
    args = parser.parse_args()

    try:
        summary = seed(args.db_url, reset=args.reset)
    except (AssertionError, ValueError) as exc:
        print(f"[seed] FAILED: {exc}", file=sys.stderr)
        return 1

    print(
        f"[seed] OK — accounts={summary['accounts']} "
        f"cards={summary['cards']} "
        f"card_products={summary['card_products']} "
        f"transactions={summary['transactions']} "
        f"ledger_entries={summary['ledger_entries']} "
        f"card_ledger_entries={summary['card_ledger_entries']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
