"""
정보계 DB view tests.

Verifies that v_infobank_account_balances and v_infobank_ledger_entries
expose correct, canonical rows after account creation and transfers.

Uses a self-contained fixture (does not depend on conftest.py db_engine)
to avoid merge conflicts with sibling tasks editing conftest.py.
"""

import pytest
from fastapi.testclient import TestClient
from financial_service.app import create_app
from financial_service.database import Base, get_db
from financial_service.migrations import apply_analytics_views, apply_audit_triggers
from sqlalchemy import create_engine, text
from sqlalchemy import event as sqla_event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def view_engine():
    """In-memory SQLite engine with tables, triggers, and analytics views."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @sqla_event.listens_for(engine, "connect")
    def set_pragma(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    apply_audit_triggers(engine)
    apply_analytics_views(engine)

    yield engine

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def view_client(view_engine):
    """TestClient wired to view_engine; yields (client, engine)."""
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=view_engine)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c, view_engine


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_account(client, owner: str, initial_balance: int = 0) -> dict:
    r = client.post(
        "/api/v1/accounts",
        json={"owner": owner, "initial_balance": initial_balance},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _transfer(client, sender: dict, receiver: dict, amount: int, key: str) -> None:
    r = client.post(
        "/api/v1/transfers",
        json={
            "sender_account_number": sender["account_number"],
            "receiver_bank_name": receiver["bank_name"],
            "receiver_account_number": receiver["account_number"],
            "amount": amount,
        },
        headers={"Idempotency-Key": key},
    )
    assert r.status_code == 200, r.text


# ── tests: v_infobank_account_balances ───────────────────────────────────────


def test_view_balance_canonical_after_transfer(view_client):
    """
    View balance must equal SUM(CREDIT) - SUM(DEBIT) after a transfer.
    Alice: initial 1000 → debit 300 → balance 700
    Bob:   initial 0    → credit 300 → balance 300
    """
    client, engine = view_client

    alice = _make_account(client, "Alice", 1000)
    bob = _make_account(client, "Bob", 0)
    _transfer(client, alice, bob, 300, "view-test-transfer-1")

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT account_id, balance, sum_credit, sum_debit "
                "FROM v_infobank_account_balances"
            )
        ).fetchall()

    bmap = {row.account_id: row for row in rows}

    assert bmap[alice["account_id"]].balance == 700
    assert bmap[alice["account_id"]].sum_credit == 1000
    assert bmap[alice["account_id"]].sum_debit == 300

    assert bmap[bob["account_id"]].balance == 300
    assert bmap[bob["account_id"]].sum_credit == 300
    assert bmap[bob["account_id"]].sum_debit == 0


def test_view_balance_matches_rest_api(view_client):
    """
    View balance must match the canonical REST API balance (SUM CREDIT - SUM DEBIT).
    Both paths must be consistent.
    """
    client, engine = view_client

    carol = _make_account(client, "Carol", 5000)
    dave = _make_account(client, "Dave", 2000)
    _transfer(client, carol, dave, 1500, "view-test-transfer-2")

    # REST API balances
    carol_api = client.get(f"/api/v1/accounts/{carol['account_id']}/balance").json()[
        "balance"
    ]
    dave_api = client.get(f"/api/v1/accounts/{dave['account_id']}/balance").json()[
        "balance"
    ]

    # View balances
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT account_id, balance "
                "FROM v_infobank_account_balances "
                "WHERE account_id IN (:c, :d)"
            ),
            {"c": carol["account_id"], "d": dave["account_id"]},
        ).fetchall()

    vmap = {row.account_id: row.balance for row in rows}

    assert vmap[carol["account_id"]] == carol_api  # 3500
    assert vmap[dave["account_id"]] == dave_api  # 3500


def test_view_zero_balance_account(view_client):
    """Account with no transactions must show zero balance in view."""
    client, engine = view_client

    empty = _make_account(client, "Empty", 0)

    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT balance, sum_credit, sum_debit, entry_count "
                "FROM v_infobank_account_balances "
                "WHERE account_id = :aid"
            ),
            {"aid": empty["account_id"]},
        ).fetchone()

    assert row is not None
    assert row.balance == 0
    assert row.sum_credit == 0
    assert row.sum_debit == 0
    assert row.entry_count == 0


def test_view_includes_all_accounts(view_client):
    """View must have exactly one row per account."""
    client, engine = view_client

    accts = [_make_account(client, f"User{i}", i * 100) for i in range(4)]

    with engine.connect() as conn:
        view_ids = {
            row.account_id
            for row in conn.execute(
                text("SELECT account_id FROM v_infobank_account_balances")
            ).fetchall()
        }

    for acct in accts:
        assert acct["account_id"] in view_ids


# ── tests: v_infobank_ledger_entries ─────────────────────────────────────────


def test_view_ledger_entries_initial_credit(view_client):
    """Account created with initial_balance must have one CREDIT entry in view."""
    client, engine = view_client

    acct = _make_account(client, "Frank", 500)

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT entry_id, account_id, entry_type, amount, owner, currency "
                "FROM v_infobank_ledger_entries "
                "WHERE account_id = :aid"
            ),
            {"aid": acct["account_id"]},
        ).fetchall()

    assert len(rows) == 1
    assert rows[0].entry_type == "CREDIT"
    assert rows[0].amount == 500
    assert rows[0].account_id == acct["account_id"]
    assert rows[0].owner == "Frank"
    assert rows[0].currency == "KRW"


def test_view_ledger_entries_after_transfer(view_client):
    """
    After a transfer sender has 2 entries (initial CREDIT + DEBIT),
    receiver has 1 entry (CREDIT).
    """
    client, engine = view_client

    sender = _make_account(client, "Grace", 800)
    receiver = _make_account(client, "Henry", 0)
    _transfer(client, sender, receiver, 200, "view-test-transfer-3")

    with engine.connect() as conn:
        sender_rows = conn.execute(
            text(
                "SELECT entry_type, amount "
                "FROM v_infobank_ledger_entries "
                "WHERE account_id = :aid "
                "ORDER BY created_at"
            ),
            {"aid": sender["account_id"]},
        ).fetchall()

        receiver_rows = conn.execute(
            text(
                "SELECT entry_type, amount "
                "FROM v_infobank_ledger_entries "
                "WHERE account_id = :aid"
            ),
            {"aid": receiver["account_id"]},
        ).fetchall()

    # Sender: initial CREDIT 800, then DEBIT 200
    assert len(sender_rows) == 2
    types = {r.entry_type for r in sender_rows}
    assert "CREDIT" in types
    assert "DEBIT" in types

    # Receiver: one CREDIT 200
    assert len(receiver_rows) == 1
    assert receiver_rows[0].entry_type == "CREDIT"
    assert receiver_rows[0].amount == 200


def test_view_ledger_no_entries_for_zero_balance_account(view_client):
    """Account created with initial_balance=0 has no ledger entries."""
    client, engine = view_client

    acct = _make_account(client, "Ida", 0)

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT entry_id FROM v_infobank_ledger_entries WHERE account_id = :aid"
            ),
            {"aid": acct["account_id"]},
        ).fetchall()

    assert len(rows) == 0
