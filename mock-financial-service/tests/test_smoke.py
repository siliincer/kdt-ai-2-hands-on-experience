"""
Smoke tests — 9 cases:
  Happy path (5): create account, get account, get balance, get transactions, transfer
  Edge cases (4): insufficient balance, negative amount, missing account, self-transfer
  + Idempotency key conflict (409)
  + Audit log immutability (DB trigger)
"""

import pytest
from sqlalchemy import text

# ── helpers ───────────────────────────────────────────────────────────────────


def make_account(client, owner="Alice", initial_balance=100_000):
    r = client.post(
        "/api/v1/accounts", json={"owner": owner, "initial_balance": initial_balance}
    )
    assert r.status_code == 201, r.text
    return r.json()


# ═══════════════════════════════════════════════════════════════════════════════
# Happy-path tests
# ═══════════════════════════════════════════════════════════════════════════════


def test_create_account(client):
    """AC Sub-1: POST /accounts → 201, schema fields present."""
    r = client.post(
        "/api/v1/accounts", json={"owner": "Alice", "initial_balance": 50_000}
    )
    assert r.status_code == 201
    body = r.json()
    assert "account_id" in body
    assert body["owner"] == "Alice"
    assert body["balance"] == 50_000
    assert body["currency"] == "KRW"
    assert "created_at" in body


def test_get_account(client):
    """AC Sub-2: GET /accounts/{id} → 200, schema fields present."""
    acct = make_account(client, "Bob", 200_000)
    r = client.get(f"/api/v1/accounts/{acct['account_id']}")
    assert r.status_code == 200
    body = r.json()
    assert body["account_id"] == acct["account_id"]
    assert body["owner"] == "Bob"
    assert body["balance"] == 200_000
    assert body["currency"] == "KRW"
    assert "created_at" in body


def test_get_account_not_found(client):
    """AC Sub-2: GET /accounts/{id} → 404 + ACCOUNT_NOT_FOUND for nonexistent ID."""
    r = client.get("/api/v1/accounts/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
    body = r.json()
    assert body["error_code"] == "ACCOUNT_NOT_FOUND"
    assert "message" in body


def test_get_balance(client):
    """GET /accounts/{id}/balance → 200, integer balance."""
    acct = make_account(client, "Carol", 30_000)
    r = client.get(f"/api/v1/accounts/{acct['account_id']}/balance")
    assert r.status_code == 200
    body = r.json()
    assert body["balance"] == 30_000
    assert body["currency"] == "KRW"


def test_get_transactions(client):
    """GET /accounts/{id}/transactions → 200, list with ledger entries."""
    acct = make_account(client, "Dave", 10_000)
    r = client.get(f"/api/v1/accounts/{acct['account_id']}/transactions")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    # initial_balance → 1 CREDIT entry
    assert len(body) >= 1
    assert body[0]["entry_type"] == "CREDIT"
    assert body[0]["amount"] == 10_000


def test_transfer_happy(client):
    """POST /transfers → 201, balances updated correctly (double-entry integrity)."""
    sender = make_account(client, "Sender", 500_000)
    receiver = make_account(client, "Receiver", 0)

    r = client.post(
        "/api/v1/transfers",
        json={
            "sender_account_id": sender["account_id"],
            "receiver_account_id": receiver["account_id"],
            "amount": 100_000,
        },
        headers={"Idempotency-Key": "transfer-key-001"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["amount"] == 100_000

    # Verify balance preservation
    s_bal = client.get(f"/api/v1/accounts/{sender['account_id']}/balance").json()[
        "balance"
    ]
    r_bal = client.get(f"/api/v1/accounts/{receiver['account_id']}/balance").json()[
        "balance"
    ]
    assert s_bal == 400_000
    assert r_bal == 100_000
    # Total preserved
    assert s_bal + r_bal == 500_000


# ═══════════════════════════════════════════════════════════════════════════════
# Edge cases
# ═══════════════════════════════════════════════════════════════════════════════


def test_transfer_insufficient_balance(client):
    """422 + INSUFFICIENT_BALANCE when sender has less than amount."""
    sender = make_account(client, "Poor", 1_000)
    receiver = make_account(client, "Rich", 0)

    r = client.post(
        "/api/v1/transfers",
        json={
            "sender_account_id": sender["account_id"],
            "receiver_account_id": receiver["account_id"],
            "amount": 999_999,
        },
        headers={"Idempotency-Key": "overdrawn-001"},
    )
    assert r.status_code == 422
    body = r.json()
    assert body["error_code"] == "INSUFFICIENT_BALANCE"
    assert "message" in body


def test_transfer_negative_amount_rejected(client):
    """422 when amount ≤ 0 (Pydantic validation)."""
    sender = make_account(client, "NegSender", 50_000)
    receiver = make_account(client, "NegReceiver", 0)

    r = client.post(
        "/api/v1/transfers",
        json={
            "sender_account_id": sender["account_id"],
            "receiver_account_id": receiver["account_id"],
            "amount": -500,
        },
        headers={"Idempotency-Key": "neg-amount-001"},
    )
    assert r.status_code == 422


def test_transfer_missing_account(client):
    """404 + ACCOUNT_NOT_FOUND for nonexistent sender."""
    receiver = make_account(client, "Receiver2", 0)
    r = client.post(
        "/api/v1/transfers",
        json={
            "sender_account_id": "00000000-0000-0000-0000-000000000000",
            "receiver_account_id": receiver["account_id"],
            "amount": 1_000,
        },
        headers={"Idempotency-Key": "ghost-sender-001"},
    )
    assert r.status_code == 404
    body = r.json()
    assert body["error_code"] == "ACCOUNT_NOT_FOUND"


def test_transfer_self_transfer(client):
    """422 + SELF_TRANSFER when sender == receiver."""
    acct = make_account(client, "SelfUser", 50_000)
    r = client.post(
        "/api/v1/transfers",
        json={
            "sender_account_id": acct["account_id"],
            "receiver_account_id": acct["account_id"],
            "amount": 1_000,
        },
        headers={"Idempotency-Key": "self-transfer-001"},
    )
    assert r.status_code == 422
    body = r.json()
    assert body["error_code"] == "SELF_TRANSFER"


# ═══════════════════════════════════════════════════════════════════════════════
# Idempotency
# ═══════════════════════════════════════════════════════════════════════════════


def test_idempotency_key_conflict(client):
    """409 when same Idempotency-Key reused with different payload."""
    sender = make_account(client, "IdemSender", 500_000)
    receiver1 = make_account(client, "IdemR1", 0)
    receiver2 = make_account(client, "IdemR2", 0)

    # First request
    r1 = client.post(
        "/api/v1/transfers",
        json={
            "sender_account_id": sender["account_id"],
            "receiver_account_id": receiver1["account_id"],
            "amount": 1_000,
        },
        headers={"Idempotency-Key": "idem-conflict-key"},
    )
    assert r1.status_code == 200

    # Same key, different payload
    r2 = client.post(
        "/api/v1/transfers",
        json={
            "sender_account_id": sender["account_id"],
            "receiver_account_id": receiver2["account_id"],
            "amount": 9_999,
        },
        headers={"Idempotency-Key": "idem-conflict-key"},
    )
    assert r2.status_code == 409
    body = r2.json()
    assert body["error_code"] == "IDEMPOTENCY_CONFLICT"


def test_idempotency_safe_replay(client):
    """Same key + same payload → 201, no double-debit."""
    sender = make_account(client, "ReplaySender", 500_000)
    receiver = make_account(client, "ReplayReceiver", 0)

    payload = {
        "sender_account_id": sender["account_id"],
        "receiver_account_id": receiver["account_id"],
        "amount": 50_000,
    }
    headers = {"Idempotency-Key": "replay-safe-001"}

    r1 = client.post("/api/v1/transfers", json=payload, headers=headers)
    assert r1.status_code == 200

    r2 = client.post("/api/v1/transfers", json=payload, headers=headers)
    assert r2.status_code == 200
    assert r1.json()["transfer_id"] == r2.json()["transfer_id"]

    # Balance unchanged after replay
    s_bal = client.get(f"/api/v1/accounts/{sender['account_id']}/balance").json()[
        "balance"
    ]
    assert s_bal == 450_000  # only deducted once


# ═══════════════════════════════════════════════════════════════════════════════
# Audit log immutability
# ═══════════════════════════════════════════════════════════════════════════════


def test_audit_log_immutable(client, db_engine):
    """DB trigger rejects UPDATE/DELETE on audit_logs."""
    make_account(client, "AuditUser", 1_000)

    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT audit_log_id FROM audit_logs LIMIT 1")
        ).fetchone()
        assert row is not None, "Audit log must exist after account creation"

        audit_id = row[0]

        # UPDATE must fail (SQLite RAISE(ABORT) → IntegrityError or OperationalError)
        from sqlalchemy.exc import DBAPIError

        with pytest.raises(DBAPIError):
            conn.execute(
                text("UPDATE audit_logs SET actor = 'hacker' WHERE audit_log_id = :id"),
                {"id": audit_id},
            )
            conn.commit()

        conn.rollback()

        # DELETE must fail
        with pytest.raises(DBAPIError):
            conn.execute(
                text("DELETE FROM audit_logs WHERE audit_log_id = :id"),
                {"id": audit_id},
            )
            conn.commit()
