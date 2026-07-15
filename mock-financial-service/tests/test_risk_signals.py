"""Tests: 이도윤 persona risk signals inside the unified 4-month mock transactions.

Risk signals (payment failure → success retry) are generated as part of
MOCK_TRANSACTIONS/MOCK_LEDGER_ENTRIES (financial_service.mock_data), not as a
separate isolated table. This file locates them by their known
(sender, receiver, amount) signature and verifies:

  1. Each of the 3 known risk scenarios has a failure row + a matching success
     retry row (same sender/receiver/amount)
  2. Failure rows have zero ledger entries (money did not move)
  3. Success rows have exactly one DEBIT + one CREDIT ledger entry
  4. Ledger entry amounts match parent transaction amount
  5. All risk-signal senders are 이도윤's account (acct-0003)
"""

import pytest
from financial_service.mock_data import (
    MOCK_TRANSACTIONS,
    make_account_rows,
    make_biller_account_rows,
    make_card_ledger_entry_rows,
    make_card_rows,
    make_external_source_account_rows,
    make_ledger_entry_rows,
    make_transaction_rows,
)
from financial_service.models import LedgerEntry, Transaction
from sqlalchemy.orm import Session

_PERSONA3_ACCT = "acct-0003-0000-0000-000000000003"
_TELECOM_BILLER = "acct-b001-0000-0000-000000000001"
_MGMT_BILLER = "acct-b004-0000-0000-000000000004"

# Known risk scenarios: (receiver, amount) — all sent by 이도윤
_RISK_SIGNATURES = [
    (_TELECOM_BILLER, 65_000),
    (_TELECOM_BILLER, 18_900),
    (_MGMT_BILLER, 350_000),
]


@pytest.fixture()
def seeded_session(db_engine):
    """In-memory DB seeded with the full mock dataset (accounts..card charges)."""
    with Session(db_engine) as session:
        session.add_all(make_account_rows())
        session.add_all(make_biller_account_rows())
        session.add_all(make_external_source_account_rows())
        session.flush()
        session.add_all(make_card_rows())
        session.flush()
        session.add_all(make_transaction_rows())
        session.flush()
        session.add_all(make_ledger_entry_rows())
        session.add_all(make_card_ledger_entry_rows())
        session.commit()
        yield session


# ── 1. Constant-level: failure + success retry pairs exist ──────────────────


def _rows_for(receiver: str, amount: int) -> list[dict]:
    return [
        t
        for t in MOCK_TRANSACTIONS
        if t["sender_account_id"] == _PERSONA3_ACCT
        and t["receiver_account_id"] == receiver
        and t["amount"] == amount
    ]


@pytest.mark.parametrize("receiver,amount", _RISK_SIGNATURES)
def test_risk_signal_has_failure_and_success_retry(receiver, amount):
    rows = _rows_for(receiver, amount)
    statuses = {r["status"] for r in rows}
    assert "failure" in statuses, (
        f"No failure row for (receiver={receiver}, amount={amount})"
    )
    assert "success" in statuses, (
        f"No success retry row for (receiver={receiver}, amount={amount})"
    )


def test_all_idempotency_keys_unique():
    keys = [t["idempotency_key"] for t in MOCK_TRANSACTIONS]
    assert len(keys) == len(set(keys)), "Duplicate idempotency_key in MOCK_TRANSACTIONS"


# ── 2. DB-level: full dataset persists, risk rows locatable ─────────────────


def test_all_transactions_in_db(seeded_session):
    count = seeded_session.query(Transaction).count()
    assert count == len(MOCK_TRANSACTIONS), (
        f"Expected {len(MOCK_TRANSACTIONS)} transactions in DB, got {count}"
    )


def test_failure_transactions_present_in_db(seeded_session):
    failures = (
        seeded_session.query(Transaction).filter(Transaction.status == "failure").all()
    )
    assert len(failures) >= 3, (
        f"Expected >= 3 failure transactions, got {len(failures)}"
    )


@pytest.mark.parametrize("receiver,amount", _RISK_SIGNATURES)
def test_failure_rows_have_no_ledger_entries_in_db(seeded_session, receiver, amount):
    failure = (
        seeded_session.query(Transaction)
        .filter(
            Transaction.sender_account_id == _PERSONA3_ACCT,
            Transaction.receiver_account_id == receiver,
            Transaction.amount == amount,
            Transaction.status == "failure",
        )
        .one()
    )
    entries = (
        seeded_session.query(LedgerEntry)
        .filter(LedgerEntry.transaction_id == failure.transaction_id)
        .all()
    )
    assert len(entries) == 0, (
        f"Failure txn {failure.transaction_id} has {len(entries)} "
        "ledger entries (expected 0)"
    )


@pytest.mark.parametrize("receiver,amount", _RISK_SIGNATURES)
def test_success_retry_has_debit_credit_pair_in_db(seeded_session, receiver, amount):
    success = (
        seeded_session.query(Transaction)
        .filter(
            Transaction.sender_account_id == _PERSONA3_ACCT,
            Transaction.receiver_account_id == receiver,
            Transaction.amount == amount,
            Transaction.status == "success",
        )
        .one()
    )
    entries = (
        seeded_session.query(LedgerEntry)
        .filter(LedgerEntry.transaction_id == success.transaction_id)
        .all()
    )
    assert len(entries) == 2, (
        f"Success txn {success.transaction_id} has {len(entries)} entries (expected 2)"
    )
    types = {e.entry_type for e in entries}
    assert types == {"DEBIT", "CREDIT"}
    for entry in entries:
        assert entry.amount == amount == success.amount
