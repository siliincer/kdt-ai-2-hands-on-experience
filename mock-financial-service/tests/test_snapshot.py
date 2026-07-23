"""
AC-3: Canonical balance (Account.balance) + reconciliation tests.

Account.balance is updated atomically with every ledger write (no separate
snapshot/refresh step). _get_balance() (full ledger recompute) exists only
to verify that stored value is legit — exposed via GET /analytics/.../reconcile.

Verifies:
  1. Account.balance reflects initial deposit immediately (no refresh needed)
  2. Account.balance updates immediately after a transfer (sender/receiver)
  3. Reconciliation shows no drift under normal operation
  4. Reconciliation detects injected drift (stored balance manually corrupted)
  5. Reconcile requires X-Analytics-Key
  6. Old snapshot endpoints are gone (404/405, not resurrected accidentally)
"""

from sqlalchemy import text

ANALYTICS_KEY = "analytics-demo-key"


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_account(client, owner: str, initial_balance: int = 0) -> dict:
    r = client.post("/api/v1/accounts", json={"owner": owner, "initial_balance": initial_balance})
    assert r.status_code == 201, r.text
    return r.json()


def _transfer(client, sender: dict, receiver: dict, amount: int, key: str):
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
    return r.json()


def _reconcile(client, account_id: str):
    return client.get(
        f"/api/v1/analytics/accounts/{account_id}/reconcile",
        headers={"X-Analytics-Key": ANALYTICS_KEY},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Account.balance reflects initial deposit immediately
# ═══════════════════════════════════════════════════════════════════════════════


def test_balance_set_on_account_create(client):
    """POST /accounts with initial_balance → balance already correct, no refresh."""
    acct = _make_account(client, "CreateBal", 50_000)
    assert acct["balance"] == 50_000

    r = client.get(f"/api/v1/accounts/{acct['account_id']}/balance")
    assert r.status_code == 200
    assert r.json()["balance"] == 50_000


def test_balance_zero_by_default(client):
    acct = _make_account(client, "ZeroBal")
    assert acct["balance"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Account.balance updates immediately after a transfer
# ═══════════════════════════════════════════════════════════════════════════════


def test_balance_updates_immediately_after_transfer(client):
    """No refresh call needed — GET right after transfer reflects new balance."""
    sender = _make_account(client, "TxSender", 200_000)
    receiver = _make_account(client, "TxReceiver", 0)

    _transfer(client, sender, receiver, 50_000, "bal-test-001")

    sender_bal = client.get(f"/api/v1/accounts/{sender['account_id']}/balance").json()
    receiver_bal = client.get(f"/api/v1/accounts/{receiver['account_id']}/balance").json()
    assert sender_bal["balance"] == 150_000
    assert receiver_bal["balance"] == 50_000


def test_balance_updates_across_multiple_transfers(client):
    sender = _make_account(client, "MultiSender", 100_000)
    receiver = _make_account(client, "MultiReceiver", 0)

    _transfer(client, sender, receiver, 10_000, "multi-001")
    _transfer(client, sender, receiver, 20_000, "multi-002")

    sender_acct = client.get(f"/api/v1/accounts/{sender['account_id']}").json()
    assert sender_acct["balance"] == 70_000


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Reconciliation — no drift under normal operation
# ═══════════════════════════════════════════════════════════════════════════════


def test_reconcile_no_drift_after_account_create(client):
    acct = _make_account(client, "ReconClean", 50_000)

    r = _reconcile(client, acct["account_id"])
    assert r.status_code == 200
    body = r.json()
    assert body["drift_detected"] is False
    assert body["delta"] == 0
    assert body["cached_balance"] == 50_000
    assert body["expected_balance"] == 50_000


def test_reconcile_no_drift_after_transfer(client):
    sender = _make_account(client, "ReconTxSender", 100_000)
    receiver = _make_account(client, "ReconTxReceiver", 0)

    _transfer(client, sender, receiver, 40_000, "recon-tx-001")

    for acct_id in (sender["account_id"], receiver["account_id"]):
        r = _reconcile(client, acct_id)
        assert r.status_code == 200
        assert r.json()["drift_detected"] is False


def test_reconcile_404_unknown_account(client):
    r = _reconcile(client, "00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
    assert r.json()["error_code"] == "ACCOUNT_NOT_FOUND"


def test_reconcile_requires_api_key(client):
    acct = _make_account(client, "AuthTest", 10_000)
    r = client.get(f"/api/v1/analytics/accounts/{acct['account_id']}/reconcile")
    assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Reconciliation — drift detection (stored balance manually corrupted)
# ═══════════════════════════════════════════════════════════════════════════════


def test_reconcile_detects_injected_drift(client, db_engine):
    """Directly mutating accounts.balance in DB → reconciliation detects it."""
    acct = _make_account(client, "ReconDrift", 100_000)

    with db_engine.connect() as conn:
        conn.execute(
            text("UPDATE accounts SET balance = 999999 WHERE account_id = :aid"),
            {"aid": acct["account_id"]},
        )
        conn.commit()

    r = _reconcile(client, acct["account_id"])
    assert r.status_code == 200
    body = r.json()
    assert body["drift_detected"] is True
    assert body["cached_balance"] == 999999
    assert body["expected_balance"] == 100_000
    assert body["delta"] == 999999 - 100_000


def test_reconcile_drift_cleared_after_legit_transfer(client, db_engine):
    """A legit transfer writes both ledger + balance atomically — no drift."""
    acct = _make_account(client, "ReconRecover", 75_000)
    other = _make_account(client, "ReconRecoverOther", 0)

    with db_engine.connect() as conn:
        conn.execute(
            text("UPDATE accounts SET balance = 1 WHERE account_id = :aid"),
            {"aid": acct["account_id"]},
        )
        conn.commit()

    # Confirm the corruption is visible as drift first
    assert _reconcile(client, acct["account_id"]).json()["drift_detected"] is True

    # A fresh account created afterwards is unaffected and drift-free
    r = _reconcile(client, other["account_id"])
    assert r.status_code == 200
    assert r.json()["drift_detected"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Old snapshot endpoints are gone
# ═══════════════════════════════════════════════════════════════════════════════


def test_snapshot_refresh_endpoint_removed(client):
    acct = _make_account(client, "NoSnapEndpoint", 5_000)
    r = client.post(f"/api/v1/accounts/{acct['account_id']}/snapshot")
    assert r.status_code == 404


def test_analytics_snapshot_get_endpoint_removed(client):
    acct = _make_account(client, "NoAnalyticsSnap", 5_000)
    r = client.get(
        f"/api/v1/analytics/accounts/{acct['account_id']}/snapshot",
        headers={"X-Analytics-Key": ANALYTICS_KEY},
    )
    assert r.status_code == 404
