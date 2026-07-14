"""
AC-2: 정보계 REST API — balance and ledger data behind X-Analytics-Key.

Verifies:
  1. GET /analytics/accounts/{id}/balance → 401 without key
  2. GET /analytics/accounts/{id}/balance → 200 with valid key, data matches canonical
  3. GET /analytics/accounts/{id}/ledger  → 401 without key
  4. GET /analytics/accounts/{id}/ledger  → 200 with valid key, entries match canonical
  5. Wrong key → 401 for both endpoints
  6. Unknown account → 404 for both endpoints (key required)
  7. Cross-path consistency: analytics balance == /api/v1/accounts/{id}/balance
"""

ANALYTICS_KEY = "analytics-demo-key"
WRONG_KEY = "wrong-key"


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_account(client, owner: str, initial_balance: int = 0) -> dict:
    r = client.post(
        "/api/v1/accounts", json={"owner": owner, "initial_balance": initial_balance}
    )
    assert r.status_code == 201, r.text
    return r.json()


def _transfer(client, sender: dict, receiver: dict, amount: int, key: str) -> dict:
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


# ═══════════════════════════════════════════════════════════════════════════════
# 1 & 5. Auth enforcement — balance endpoint
# ═══════════════════════════════════════════════════════════════════════════════


def test_analytics_balance_requires_key(client):
    """GET /analytics/accounts/{id}/balance → 401 without X-Analytics-Key."""
    acct = _make_account(client, "AuthBalNoKey", 10_000)
    r = client.get(f"/api/v1/analytics/accounts/{acct['account_id']}/balance")
    assert r.status_code == 401
    body = r.json()
    assert body["error_code"] == "UNAUTHORIZED"


def test_analytics_balance_wrong_key_rejected(client):
    """GET /analytics/accounts/{id}/balance → 401 with wrong key."""
    acct = _make_account(client, "AuthBalWrongKey", 10_000)
    r = client.get(
        f"/api/v1/analytics/accounts/{acct['account_id']}/balance",
        headers={"X-Analytics-Key": WRONG_KEY},
    )
    assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Analytics balance correctness
# ═══════════════════════════════════════════════════════════════════════════════


def test_analytics_balance_initial_deposit(client):
    """Analytics balance equals initial_balance for freshly created account."""
    acct = _make_account(client, "BalInitial", 50_000)

    r = client.get(
        f"/api/v1/analytics/accounts/{acct['account_id']}/balance",
        headers={"X-Analytics-Key": ANALYTICS_KEY},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["account_id"] == acct["account_id"]
    assert body["balance"] == 50_000
    assert body["currency"] == "KRW"


def test_analytics_balance_after_transfer(client):
    """Analytics balance reflects deducted amount after a transfer."""
    sender = _make_account(client, "BalSender", 100_000)
    receiver = _make_account(client, "BalReceiver", 0)
    _transfer(
        client,
        sender,
        receiver,
        30_000,
        "analytics-bal-001",
    )

    r_sender = client.get(
        f"/api/v1/analytics/accounts/{sender['account_id']}/balance",
        headers={"X-Analytics-Key": ANALYTICS_KEY},
    )
    r_receiver = client.get(
        f"/api/v1/analytics/accounts/{receiver['account_id']}/balance",
        headers={"X-Analytics-Key": ANALYTICS_KEY},
    )

    assert r_sender.status_code == 200
    assert r_receiver.status_code == 200
    assert r_sender.json()["balance"] == 70_000
    assert r_receiver.json()["balance"] == 30_000


# ═══════════════════════════════════════════════════════════════════════════════
# 3 & 5. Auth enforcement — ledger endpoint
# ═══════════════════════════════════════════════════════════════════════════════


def test_analytics_ledger_requires_key(client):
    """GET /analytics/accounts/{id}/ledger → 401 without X-Analytics-Key."""
    acct = _make_account(client, "AuthLedNoKey", 5_000)
    r = client.get(f"/api/v1/analytics/accounts/{acct['account_id']}/ledger")
    assert r.status_code == 401
    body = r.json()
    assert body["error_code"] == "UNAUTHORIZED"


def test_analytics_ledger_wrong_key_rejected(client):
    """GET /analytics/accounts/{id}/ledger → 401 with wrong key."""
    acct = _make_account(client, "AuthLedWrongKey", 5_000)
    r = client.get(
        f"/api/v1/analytics/accounts/{acct['account_id']}/ledger",
        headers={"X-Analytics-Key": WRONG_KEY},
    )
    assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Analytics ledger correctness
# ═══════════════════════════════════════════════════════════════════════════════


def test_analytics_ledger_initial_credit_entry(client):
    """Account with initial_balance has one CREDIT entry via analytics endpoint."""
    acct = _make_account(client, "LedCredit", 20_000)

    r = client.get(
        f"/api/v1/analytics/accounts/{acct['account_id']}/ledger",
        headers={"X-Analytics-Key": ANALYTICS_KEY},
    )
    assert r.status_code == 200
    entries = r.json()
    assert len(entries) == 1
    assert entries[0]["entry_type"] == "CREDIT"
    assert entries[0]["amount"] == 20_000


def test_analytics_ledger_after_transfer(client):
    """Sender has CREDIT + DEBIT entries; receiver has CREDIT entry after transfer."""
    sender = _make_account(client, "LedSender", 80_000)
    receiver = _make_account(client, "LedReceiver", 0)
    _transfer(
        client,
        sender,
        receiver,
        25_000,
        "analytics-led-001",
    )

    r_sender = client.get(
        f"/api/v1/analytics/accounts/{sender['account_id']}/ledger",
        headers={"X-Analytics-Key": ANALYTICS_KEY},
    )
    r_receiver = client.get(
        f"/api/v1/analytics/accounts/{receiver['account_id']}/ledger",
        headers={"X-Analytics-Key": ANALYTICS_KEY},
    )

    assert r_sender.status_code == 200
    assert r_receiver.status_code == 200

    sender_entries = r_sender.json()
    receiver_entries = r_receiver.json()

    assert len(sender_entries) == 2  # initial CREDIT + DEBIT
    sender_types = {e["entry_type"] for e in sender_entries}
    assert "CREDIT" in sender_types
    assert "DEBIT" in sender_types

    assert len(receiver_entries) == 1
    assert receiver_entries[0]["entry_type"] == "CREDIT"
    assert receiver_entries[0]["amount"] == 25_000


def test_analytics_ledger_zero_balance_account_empty(client):
    """Account with initial_balance=0 has no ledger entries."""
    acct = _make_account(client, "LedEmpty", 0)

    r = client.get(
        f"/api/v1/analytics/accounts/{acct['account_id']}/ledger",
        headers={"X-Analytics-Key": ANALYTICS_KEY},
    )
    assert r.status_code == 200
    assert r.json() == []


# ═══════════════════════════════════════════════════════════════════════════════
# 6. 404 for unknown account (with valid key)
# ═══════════════════════════════════════════════════════════════════════════════


def test_analytics_balance_404_unknown_account(client):
    """Analytics balance endpoint → 404 ACCOUNT_NOT_FOUND for non-existent account."""
    r = client.get(
        "/api/v1/analytics/accounts/00000000-0000-0000-0000-000000000000/balance",
        headers={"X-Analytics-Key": ANALYTICS_KEY},
    )
    assert r.status_code == 404
    assert r.json()["error_code"] == "ACCOUNT_NOT_FOUND"


def test_analytics_ledger_404_unknown_account(client):
    """Analytics ledger endpoint → 404 ACCOUNT_NOT_FOUND for non-existent account."""
    r = client.get(
        "/api/v1/analytics/accounts/00000000-0000-0000-0000-000000000000/ledger",
        headers={"X-Analytics-Key": ANALYTICS_KEY},
    )
    assert r.status_code == 404
    assert r.json()["error_code"] == "ACCOUNT_NOT_FOUND"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Cross-path consistency: analytics == canonical
# ═══════════════════════════════════════════════════════════════════════════════


def test_analytics_balance_matches_canonical_endpoint(client):
    """Analytics balance == canonical /accounts/{id}/balance (unauthenticated)."""
    alice = _make_account(client, "CrossAlice", 200_000)
    bob = _make_account(client, "CrossBob", 50_000)
    _transfer(client, alice, bob, 75_000, "cross-path-001")

    for acct_id in (alice["account_id"], bob["account_id"]):
        canonical_r = client.get(f"/api/v1/accounts/{acct_id}/balance")
        analytics_r = client.get(
            f"/api/v1/analytics/accounts/{acct_id}/balance",
            headers={"X-Analytics-Key": ANALYTICS_KEY},
        )

        assert canonical_r.status_code == 200
        assert analytics_r.status_code == 200
        assert canonical_r.json()["balance"] == analytics_r.json()["balance"], (
            f"Balance mismatch for {acct_id}: "
            f"canonical={canonical_r.json()['balance']}, "
            f"analytics={analytics_r.json()['balance']}"
        )


def test_analytics_ledger_matches_canonical_endpoint(client):
    """Analytics ledger matches /api/v1/accounts/{id}/transactions (count + types)."""
    acct = _make_account(client, "CrossLedger", 60_000)
    other = _make_account(client, "CrossLedgerOther", 0)
    _transfer(client, acct, other, 15_000, "cross-path-002")

    canonical_r = client.get(f"/api/v1/accounts/{acct['account_id']}/transactions")
    analytics_r = client.get(
        f"/api/v1/analytics/accounts/{acct['account_id']}/ledger",
        headers={"X-Analytics-Key": ANALYTICS_KEY},
    )

    assert canonical_r.status_code == 200
    assert analytics_r.status_code == 200

    canonical_entries = canonical_r.json()
    analytics_entries = analytics_r.json()

    assert len(canonical_entries) == len(analytics_entries)

    # entry_ids should be identical sets
    canonical_ids = {e["entry_id"] for e in canonical_entries}
    analytics_ids = {e["entry_id"] for e in analytics_entries}
    assert canonical_ids == analytics_ids
