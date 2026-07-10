"""
EOD 일일 마감(daily closing) 배치 테스트.

Verifies:
  1. POST /batch/daily-close — 계좌당 1행 insert, 필드 계약
  2. 같은 business_date 재실행 시 idempotent (중복 행 없음)
  3. 다른 business_date(백필) 실행 시 새 행 추가 (이력 누적)
  4. closing_balance / sum_credit / sum_debit 정확성
  5. GET /batch/accounts/{id}/daily-closings — 이력 조회, 404 처리
"""

from sqlalchemy import text

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_account(client, owner: str, initial_balance: int = 0) -> dict:
    r = client.post(
        "/api/v1/accounts", json={"owner": owner, "initial_balance": initial_balance}
    )
    assert r.status_code == 201, r.text
    return r.json()


def _transfer(client, sender_id: str, receiver_id: str, amount: int, key: str):
    r = client.post(
        "/api/v1/transfers",
        json={
            "sender_account_id": sender_id,
            "receiver_account_id": receiver_id,
            "amount": amount,
        },
        headers={"Idempotency-Key": key},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _run_close(client, business_date: str | None = None):
    params = {"business_date": business_date} if business_date else {}
    r = client.post("/api/v1/batch/daily-close", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _count_closing_rows(db_engine, account_id: str) -> int:
    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT COUNT(*) FROM daily_closing_snapshots WHERE account_id = :aid"
            ),
            {"aid": account_id},
        ).fetchone()
    return row[0]


# ═══════════════════════════════════════════════════════════════════════════════
# 1. POST /batch/daily-close — schema contract
# ═══════════════════════════════════════════════════════════════════════════════


def test_daily_close_returns_200_and_fields(client):
    _make_account(client, "CloseUser1", 50_000)
    body = _run_close(client)
    for field in ("business_date", "accounts_closed", "snapshots"):
        assert field in body, f"Missing field: {field}"
    assert body["accounts_closed"] >= 1


def test_daily_close_snapshot_fields(client):
    acct = _make_account(client, "CloseUser2", 30_000)
    body = _run_close(client)
    snap = next(s for s in body["snapshots"] if s["account_id"] == acct["account_id"])
    for field in (
        "account_id",
        "business_date",
        "closing_balance",
        "sum_credit",
        "sum_debit",
        "last_entry_rowid",
        "created_at",
    ):
        assert field in snap, f"Missing snapshot field: {field}"
    assert snap["closing_balance"] == 30_000


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Idempotency — same business_date, no duplicate rows
# ═══════════════════════════════════════════════════════════════════════════════


def test_daily_close_idempotent_same_day(client, db_engine):
    acct = _make_account(client, "CloseIdem1", 10_000)

    _run_close(client)
    _run_close(client)
    _run_close(client)

    count = _count_closing_rows(db_engine, acct["account_id"])
    assert count == 1, f"Expected 1 closing row after 3 runs same day, got {count}"


def test_daily_close_second_run_reports_zero_new_closures(client):
    _make_account(client, "CloseIdem2", 10_000)

    first = _run_close(client)
    second = _run_close(client)

    assert first["accounts_closed"] >= 1
    assert second["accounts_closed"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Backfill — different business_date accumulates history
# ═══════════════════════════════════════════════════════════════════════════════


def test_daily_close_different_business_date_adds_row(client, db_engine):
    acct = _make_account(client, "CloseHist1", 20_000)

    _run_close(client)  # today
    body = _run_close(client, business_date="2020-01-01")  # backfill day

    assert body["business_date"] == "2020-01-01"
    count = _count_closing_rows(db_engine, acct["account_id"])
    assert count == 2, f"Expected 2 closing rows across 2 business dates, got {count}"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Correctness — closing_balance / sum_credit / sum_debit
# ═══════════════════════════════════════════════════════════════════════════════


def test_daily_close_balance_after_transfer(client):
    sender = _make_account(client, "CloseTxS", 200_000)
    receiver = _make_account(client, "CloseTxR", 0)

    _transfer(
        client, sender["account_id"], receiver["account_id"], 60_000, "close-tx-001"
    )

    body = _run_close(client)
    sender_snap = next(
        s for s in body["snapshots"] if s["account_id"] == sender["account_id"]
    )
    receiver_snap = next(
        s for s in body["snapshots"] if s["account_id"] == receiver["account_id"]
    )

    assert sender_snap["closing_balance"] == 140_000
    assert sender_snap["sum_credit"] == 200_000
    assert sender_snap["sum_debit"] == 60_000

    assert receiver_snap["closing_balance"] == 60_000
    assert receiver_snap["sum_credit"] == 60_000
    assert receiver_snap["sum_debit"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 5. GET /batch/accounts/{id}/daily-closings — history query
# ═══════════════════════════════════════════════════════════════════════════════


def test_list_daily_closings_returns_history(client):
    acct = _make_account(client, "CloseListA", 15_000)

    _run_close(client)
    _run_close(client, business_date="2020-01-01")

    r = client.get(f"/api/v1/batch/accounts/{acct['account_id']}/daily-closings")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    dates = {row["business_date"] for row in body}
    assert "2020-01-01" in dates


def test_list_daily_closings_404_for_unknown_account(client):
    r = client.get(
        "/api/v1/batch/accounts/00000000-0000-0000-0000-000000000000/daily-closings"
    )
    assert r.status_code == 404
    assert r.json()["error_code"] == "ACCOUNT_NOT_FOUND"
