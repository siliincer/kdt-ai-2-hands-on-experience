"""
AC-3: Snapshot refresh tests.

Verifies:
  1. POST /accounts/{id}/snapshot returns 200 with snapshot fields
  2. Single-row semantics — calling refresh N times leaves exactly 1 row per account
  3. Watermark (last_entry_rowid) advances after new ledger entries
  4. cached_balance equals canonical balance (SUM CREDIT - SUM DEBIT) at refresh time
  5. Analytics GET /analytics/accounts/{id}/snapshot returns same data (API key req.)
  6. Reconciliation detects injected drift
"""

from sqlalchemy import text

ANALYTICS_KEY = "analytics-demo-key"


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_account(client, owner: str, initial_balance: int = 0) -> dict:
    r = client.post(
        "/api/v1/accounts", json={"owner": owner, "initial_balance": initial_balance}
    )
    assert r.status_code == 201, r.text
    return r.json()


def _refresh(client, account_id: str) -> dict:
    r = client.post(f"/api/v1/accounts/{account_id}/snapshot")
    assert r.status_code == 200, r.text
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


def _count_snapshot_rows(db_engine, account_id: str) -> int:
    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT COUNT(*) FROM balance_snapshots WHERE account_id = :aid"),
            {"aid": account_id},
        ).fetchone()
    return row[0]


# ═══════════════════════════════════════════════════════════════════════════════
# 1. POST /accounts/{id}/snapshot — schema contract
# ═══════════════════════════════════════════════════════════════════════════════


def test_snapshot_returns_200_and_fields(client):
    """Refresh endpoint returns 200 with all required snapshot fields."""
    acct = _make_account(client, "SnapUser", 50_000)
    r = client.post(f"/api/v1/accounts/{acct['account_id']}/snapshot")
    assert r.status_code == 200
    body = r.json()
    for field in (
        "account_id",
        "cached_balance",
        "last_entry_rowid",
        "sum_credit",
        "sum_debit",
        "refreshed_at",
    ):
        assert field in body, f"Missing field: {field}"
    assert body["account_id"] == acct["account_id"]


def test_snapshot_404_for_unknown_account(client):
    """Refresh on non-existent account → 404 ACCOUNT_NOT_FOUND."""
    r = client.post("/api/v1/accounts/00000000-0000-0000-0000-000000000000/snapshot")
    assert r.status_code == 404
    assert r.json()["error_code"] == "ACCOUNT_NOT_FOUND"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Single-row overwrite semantics
# ═══════════════════════════════════════════════════════════════════════════════


def test_snapshot_single_row_after_first_refresh(client, db_engine):
    """After first refresh: exactly 1 row in balance_snapshots."""
    acct = _make_account(client, "SingleRow1", 10_000)
    _refresh(client, acct["account_id"])

    count = _count_snapshot_rows(db_engine, acct["account_id"])
    assert count == 1, f"Expected 1 snapshot row, got {count}"


def test_snapshot_still_single_row_after_repeated_refresh(client, db_engine):
    """Calling refresh 3 times → still exactly 1 row (overwrite, never append)."""
    acct = _make_account(client, "SingleRow2", 20_000)

    for _ in range(3):
        _refresh(client, acct["account_id"])

    count = _count_snapshot_rows(db_engine, acct["account_id"])
    assert count == 1, f"Expected 1 snapshot row after 3 refreshes, got {count}"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Watermark advances after new ledger entries
# ═══════════════════════════════════════════════════════════════════════════════


def test_snapshot_watermark_advances_after_transfer(client, db_engine):
    """last_entry_rowid increases after a new transfer adds ledger entries."""
    sender = _make_account(client, "WmSender", 100_000)
    receiver = _make_account(client, "WmReceiver", 0)

    # First snapshot — captures initial credit entry only
    snap1 = _refresh(client, sender["account_id"])
    wm1 = snap1["last_entry_rowid"]
    assert wm1 is not None

    # Transfer adds a DEBIT to sender
    _transfer(client, sender, receiver, 30_000, "wm-test-001")

    # Second snapshot — must have higher watermark
    snap2 = _refresh(client, sender["account_id"])
    wm2 = snap2["last_entry_rowid"]

    assert wm2 is not None
    assert wm2 > wm1, f"Watermark should advance: {wm1} → {wm2}"


def test_snapshot_watermark_unchanged_if_no_new_entries(client, db_engine):
    """Refreshing twice with no ledger activity → same watermark."""
    acct = _make_account(client, "WmStable", 5_000)

    snap1 = _refresh(client, acct["account_id"])
    snap2 = _refresh(client, acct["account_id"])

    assert snap1["last_entry_rowid"] == snap2["last_entry_rowid"]


# ═══════════════════════════════════════════════════════════════════════════════
# 4. cached_balance correctness
# ═══════════════════════════════════════════════════════════════════════════════


def test_snapshot_cached_balance_matches_canonical(client):
    """cached_balance in snapshot equals canonical balance from /balance endpoint."""
    acct = _make_account(client, "BalMatch", 80_000)
    snap = _refresh(client, acct["account_id"])

    canonical = client.get(f"/api/v1/accounts/{acct['account_id']}/balance").json()[
        "balance"
    ]
    assert snap["cached_balance"] == canonical


def test_snapshot_cached_balance_after_transfer(client):
    """After transfer and refresh, cached_balance reflects deducted amount."""
    sender = _make_account(client, "CacheSender", 200_000)
    receiver = _make_account(client, "CacheReceiver", 0)

    _transfer(client, sender, receiver, 50_000, "cache-test-001")

    snap = _refresh(client, sender["account_id"])
    assert snap["cached_balance"] == 150_000

    snap_r = _refresh(client, receiver["account_id"])
    assert snap_r["cached_balance"] == 50_000


def test_snapshot_sum_credit_and_debit_correct(client):
    """sum_credit and sum_debit stored in snapshot are correct."""
    sender = _make_account(client, "SumSender", 100_000)
    receiver = _make_account(client, "SumReceiver", 0)

    _transfer(client, sender, receiver, 40_000, "sum-test-001")

    snap = _refresh(client, sender["account_id"])
    # sender: 1 CREDIT (initial 100k) + 1 DEBIT (40k)
    assert snap["sum_credit"] == 100_000
    assert snap["sum_debit"] == 40_000
    assert snap["cached_balance"] == 60_000


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Analytics read endpoint (API key required)
# ═══════════════════════════════════════════════════════════════════════════════


def test_analytics_snapshot_get_requires_api_key(client):
    """GET /analytics/accounts/{id}/snapshot → 401 without key."""
    acct = _make_account(client, "AuthTest1", 10_000)
    _refresh(client, acct["account_id"])

    r = client.get(f"/api/v1/analytics/accounts/{acct['account_id']}/snapshot")
    assert r.status_code == 401


def test_analytics_snapshot_get_returns_snapshot(client):
    """GET /analytics/accounts/{id}/snapshot with valid key → 200, same data."""
    acct = _make_account(client, "AuthTest2", 30_000)
    snap_post = _refresh(client, acct["account_id"])

    r = client.get(
        f"/api/v1/analytics/accounts/{acct['account_id']}/snapshot",
        headers={"X-Analytics-Key": ANALYTICS_KEY},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["account_id"] == acct["account_id"]
    assert body["cached_balance"] == snap_post["cached_balance"]
    assert body["last_entry_rowid"] == snap_post["last_entry_rowid"]


def test_analytics_snapshot_get_404_if_not_refreshed(client):
    """GET analytics snapshot before refresh → 404 SNAPSHOT_NOT_FOUND."""
    acct = _make_account(client, "NoSnap", 5_000)

    r = client.get(
        f"/api/v1/analytics/accounts/{acct['account_id']}/snapshot",
        headers={"X-Analytics-Key": ANALYTICS_KEY},
    )
    assert r.status_code == 404
    assert r.json()["error_code"] == "SNAPSHOT_NOT_FOUND"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Reconciliation — drift detection
# ═══════════════════════════════════════════════════════════════════════════════


def test_reconcile_no_drift_after_fresh_snapshot(client):
    """Reconciliation shows drift_detected=False immediately after refresh."""
    acct = _make_account(client, "ReconClean", 50_000)
    _refresh(client, acct["account_id"])

    r = client.get(
        f"/api/v1/analytics/accounts/{acct['account_id']}/reconcile",
        headers={"X-Analytics-Key": ANALYTICS_KEY},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["drift_detected"] is False
    assert body["delta"] == 0


def test_reconcile_detects_injected_drift(client, db_engine):
    """Directly mutating cached_balance in DB → reconciliation detects drift."""
    acct = _make_account(client, "ReconDrift", 100_000)
    _refresh(client, acct["account_id"])

    # Inject drift: manually corrupt cached_balance (simulates stale cache)
    with db_engine.connect() as conn:
        conn.execute(
            text(
                "UPDATE balance_snapshots SET cached_balance = 999999 "
                "WHERE account_id = :aid"
            ),
            {"aid": acct["account_id"]},
        )
        conn.commit()

    r = client.get(
        f"/api/v1/analytics/accounts/{acct['account_id']}/reconcile",
        headers={"X-Analytics-Key": ANALYTICS_KEY},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["drift_detected"] is True
    assert body["cached_balance"] == 999999
    assert body["expected_balance"] == 100_000
    assert body["delta"] == 999999 - 100_000


def test_reconcile_drift_cleared_after_refresh(client, db_engine):
    """After re-running refresh following injected drift, drift_detected is False."""
    acct = _make_account(client, "ReconRecover", 75_000)
    _refresh(client, acct["account_id"])

    # Corrupt cache
    with db_engine.connect() as conn:
        conn.execute(
            text(
                "UPDATE balance_snapshots SET cached_balance = 1 "
                "WHERE account_id = :aid"
            ),
            {"aid": acct["account_id"]},
        )
        conn.commit()

    # Re-refresh overwrites corruption
    _refresh(client, acct["account_id"])

    r = client.get(
        f"/api/v1/analytics/accounts/{acct['account_id']}/reconcile",
        headers={"X-Analytics-Key": ANALYTICS_KEY},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["drift_detected"] is False
    assert body["cached_balance"] == 75_000
