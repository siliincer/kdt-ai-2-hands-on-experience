"""
AC-5: Cross-path equality — DB view and analytics REST API return identical data.

Verifies that v_infobank_account_balances (direct DB read) and
GET /api/v1/analytics/accounts/{id}/balance (analytics REST) agree on:
  - canonical balance after account creation and transfers
  - zero-balance account

Verifies that v_infobank_ledger_entries (direct DB read) and
GET /api/v1/analytics/accounts/{id}/ledger (analytics REST) agree on:
  - entry IDs, entry_type, and amount for every row
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

ANALYTICS_KEY = "analytics-demo-key"


# ── fixture ───────────────────────────────────────────────────────────────────


@pytest.fixture()
def xp_engine():
    """In-memory SQLite with tables, audit triggers, and analytics views."""
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
def xp_client(xp_engine):
    """TestClient wired to xp_engine; yields (client, engine)."""
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=xp_engine)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c, xp_engine


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


def _view_balance(engine, account_id: str) -> int:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT balance FROM v_infobank_account_balances "
                "WHERE account_id = :aid"
            ),
            {"aid": account_id},
        ).fetchone()
    assert row is not None, f"Account {account_id} not in view"
    return row.balance


def _rest_balance(client, account_id: str) -> int:
    r = client.get(
        f"/api/v1/analytics/accounts/{account_id}/balance",
        headers={"X-Analytics-Key": ANALYTICS_KEY},
    )
    assert r.status_code == 200, r.text
    return r.json()["balance"]


def _view_ledger(engine, account_id: str) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT entry_id, entry_type, amount "
                "FROM v_infobank_ledger_entries "
                "WHERE account_id = :aid "
                "ORDER BY entry_id"
            ),
            {"aid": account_id},
        ).fetchall()
    return [
        {"entry_id": r.entry_id, "entry_type": r.entry_type, "amount": r.amount}
        for r in rows
    ]


def _rest_ledger(client, account_id: str) -> list[dict]:
    r = client.get(
        f"/api/v1/analytics/accounts/{account_id}/ledger",
        params={"limit": 200},
        headers={"X-Analytics-Key": ANALYTICS_KEY},
    )
    assert r.status_code == 200, r.text
    return sorted(
        [
            {
                "entry_id": e["entry_id"],
                "entry_type": e["entry_type"],
                "amount": e["amount"],
            }
            for e in r.json()
        ],
        key=lambda x: x["entry_id"],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Balance cross-path equality
# ═══════════════════════════════════════════════════════════════════════════════


def test_crosspath_balance_initial_deposit(xp_client):
    """View balance == analytics REST balance for freshly created account."""
    client, engine = xp_client
    acct = _make_account(client, "XPInitial", 42_000)
    acct_id = acct["account_id"]

    assert _view_balance(engine, acct_id) == _rest_balance(client, acct_id) == 42_000


def test_crosspath_balance_after_transfer(xp_client):
    """View balance == analytics REST balance after a transfer for both sides."""
    client, engine = xp_client
    sender = _make_account(client, "XPSender", 100_000)
    receiver = _make_account(client, "XPReceiver", 0)
    sender_id = sender["account_id"]
    receiver_id = receiver["account_id"]
    _transfer(client, sender, receiver, 40_000, "xp-bal-001")

    sender_view = _view_balance(engine, sender_id)
    sender_rest = _rest_balance(client, sender_id)
    assert sender_view == sender_rest, (
        f"Sender balance mismatch: view={sender_view}, rest={sender_rest}"
    )
    assert sender_view == 60_000

    receiver_view = _view_balance(engine, receiver_id)
    receiver_rest = _rest_balance(client, receiver_id)
    assert receiver_view == receiver_rest, (
        f"Receiver balance mismatch: view={receiver_view}, rest={receiver_rest}"
    )
    assert receiver_view == 40_000


def test_crosspath_balance_zero_account(xp_client):
    """View balance == analytics REST balance == 0 for zero-balance account."""
    client, engine = xp_client
    acct = _make_account(client, "XPZero", 0)
    acct_id = acct["account_id"]

    assert _view_balance(engine, acct_id) == _rest_balance(client, acct_id) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Ledger cross-path equality
# ═══════════════════════════════════════════════════════════════════════════════


def test_crosspath_ledger_initial_credit(xp_client):
    """View ledger entry_id/type/amount == analytics REST ledger for single CREDIT."""
    client, engine = xp_client
    acct = _make_account(client, "XPLedCredit", 20_000)
    acct_id = acct["account_id"]

    view_entries = _view_ledger(engine, acct_id)
    rest_entries = _rest_ledger(client, acct_id)

    assert view_entries == rest_entries, (
        f"Ledger mismatch:\n  view={view_entries}\n  rest={rest_entries}"
    )
    assert len(view_entries) == 1
    assert view_entries[0]["entry_type"] == "CREDIT"
    assert view_entries[0]["amount"] == 20_000


def test_crosspath_ledger_after_transfer(xp_client):
    """View ledger entry_ids/types/amounts == analytics REST ledger after transfer."""
    client, engine = xp_client
    sender = _make_account(client, "XPLedSender", 80_000)
    receiver = _make_account(client, "XPLedReceiver", 0)
    sender_id = sender["account_id"]
    receiver_id = receiver["account_id"]
    _transfer(client, sender, receiver, 30_000, "xp-led-001")

    for acct_id, label in [(sender_id, "sender"), (receiver_id, "receiver")]:
        view_entries = _view_ledger(engine, acct_id)
        rest_entries = _rest_ledger(client, acct_id)
        assert view_entries == rest_entries, (
            f"{label} ledger mismatch:\n  view={view_entries}\n  rest={rest_entries}"
        )

    sender_view = _view_ledger(engine, sender_id)
    assert len(sender_view) == 2
    assert {e["entry_type"] for e in sender_view} == {"CREDIT", "DEBIT"}

    receiver_view = _view_ledger(engine, receiver_id)
    assert len(receiver_view) == 1
    assert receiver_view[0]["entry_type"] == "CREDIT"
    assert receiver_view[0]["amount"] == 30_000


def test_crosspath_ledger_empty_account(xp_client):
    """Both paths return empty list for zero-balance account with no entries."""
    client, engine = xp_client
    acct = _make_account(client, "XPLedEmpty", 0)
    acct_id = acct["account_id"]

    view_entries = _view_ledger(engine, acct_id)
    rest_entries = _rest_ledger(client, acct_id)

    assert view_entries == rest_entries == []


def test_crosspath_multiple_transfers_consistency(xp_client):
    """View and REST agree after multiple transfers — IDs, types, amounts identical."""
    client, engine = xp_client
    alice = _make_account(client, "XPAlice", 500_000)
    bob = _make_account(client, "XPBob", 100_000)
    carol = _make_account(client, "XPCarol", 0)
    alice_id = alice["account_id"]
    bob_id = bob["account_id"]
    carol_id = carol["account_id"]

    _transfer(client, alice, bob, 50_000, "xp-multi-001")
    _transfer(client, alice, carol, 75_000, "xp-multi-002")
    _transfer(client, bob, carol, 20_000, "xp-multi-003")

    for acct_id, label in [(alice_id, "alice"), (bob_id, "bob"), (carol_id, "carol")]:
        vb = _view_balance(engine, acct_id)
        rb = _rest_balance(client, acct_id)
        assert vb == rb, f"{label} balance: view={vb} rest={rb}"

        vl = _view_ledger(engine, acct_id)
        rl = _rest_ledger(client, acct_id)
        assert vl == rl, f"{label} ledger mismatch:\n  view={vl}\n  rest={rl}"
