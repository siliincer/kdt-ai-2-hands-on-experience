"""
PR29(feat/connect_fe_be_agent) backend 코드의 TODO(계정계) 주석 6건 해소분 검증.

1. GET  /accounts/by-number/{account_number}                — 계좌번호 기반 조회
2. PATCH /accounts/{account_id}/alias                        — alias write endpoint
3. GET  /accounts/{id}/transactions, /analytics/.../ledger   — 상대방(counterparty) 정보
4. GET  /accounts/{id}/transactions, /analytics/.../ledger   — transaction_type 구분
5. GET  /accounts/{id}/transactions, /analytics/.../ledger   — start_date/end_date 필터
6. GET  /analytics/accounts/{id}/transfers/daily-total       — 계좌 기준 일일 이체 합계
"""

from datetime import date, datetime, timedelta, timezone

ANALYTICS_KEY = "analytics-demo-key"


def _today_utc() -> date:
    """서버는 날짜 필터를 전부 UTC 기준으로 계산한다(_day_range_utc).
    date.today()는 로컬 타임존이라 어긋날 수 있어 테스트도 UTC로 맞춘다."""
    return datetime.now(timezone.utc).date()


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
# 1. GET /accounts/by-number/{account_number}
# ═══════════════════════════════════════════════════════════════════════════════


class TestAccountLookupByNumber:
    def test_found_returns_owner_and_account_info(self, client):
        acct = _make_account(client, "LookupOwner", 1_000)
        r = client.get(f"/api/v1/accounts/by-number/{acct['account_number']}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["account_id"] == acct["account_id"]
        assert body["owner"] == "LookupOwner"
        assert body["account_number"] == acct["account_number"]

    def test_not_found_returns_404(self, client):
        r = client.get("/api/v1/accounts/by-number/000-000-000000")
        assert r.status_code == 404
        assert r.json()["error_code"] == "ACCOUNT_NOT_FOUND"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. PATCH /accounts/{account_id}/alias
# ═══════════════════════════════════════════════════════════════════════════════


class TestAccountAliasUpdate:
    def test_update_alias_persists(self, client):
        acct = _make_account(client, "AliasOwner")
        assert acct["alias"] is None

        r = client.patch(
            f"/api/v1/accounts/{acct['account_id']}/alias",
            json={"alias": "생활비 통장"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["alias"] == "생활비 통장"

        # persisted — GET reflects it too
        r2 = client.get(f"/api/v1/accounts/{acct['account_id']}")
        assert r2.json()["alias"] == "생활비 통장"

    def test_unknown_account_404(self, client):
        r = client.patch(
            "/api/v1/accounts/does-not-exist/alias", json={"alias": "x"}
        )
        assert r.status_code == 404

    def test_empty_alias_rejected(self, client):
        acct = _make_account(client, "AliasEmpty")
        r = client.patch(
            f"/api/v1/accounts/{acct['account_id']}/alias", json={"alias": ""}
        )
        assert r.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════════
# 3 & 4. counterparty 정보 + transaction_type — /transactions, /analytics/.../ledger
# ═══════════════════════════════════════════════════════════════════════════════


class TestLedgerEnrichment:
    def test_transfer_entries_carry_counterparty_and_type(self, client):
        sender = _make_account(client, "EnrichSender", 100_000)
        receiver = _make_account(client, "EnrichReceiver", 0)
        _transfer(client, sender, receiver, 30_000, "enrich-1")

        r = client.get(f"/api/v1/accounts/{sender['account_id']}/transactions")
        assert r.status_code == 200, r.text
        entries = r.json()
        debit = next(e for e in entries if e["entry_type"] == "DEBIT")
        assert debit["transaction_type"] == "TRANSFER"
        assert debit["counterparty_account_id"] == receiver["account_id"]
        assert debit["counterparty_account_number"] == receiver["account_number"]
        assert debit["counterparty_owner"] == "EnrichReceiver"

        r_recv = client.get(f"/api/v1/accounts/{receiver['account_id']}/transactions")
        credit = next(e for e in r_recv.json() if e["entry_type"] == "CREDIT")
        assert credit["counterparty_owner"] == "EnrichSender"

    def test_seed_deposit_has_no_counterparty(self, client):
        """계좌 개설 초기입금(sender==receiver인 합성 거래)은 진짜 상대방이 없다."""
        acct = _make_account(client, "SeedOnly", 50_000)
        r = client.get(f"/api/v1/accounts/{acct['account_id']}/transactions")
        entries = r.json()
        seed_entry = next(e for e in entries if e["entry_type"] == "CREDIT")
        assert seed_entry["counterparty_account_id"] is None
        assert seed_entry["counterparty_owner"] is None

    def test_analytics_ledger_matches_same_enrichment(self, client):
        sender = _make_account(client, "AnaEnrichSender", 100_000)
        receiver = _make_account(client, "AnaEnrichReceiver", 0)
        _transfer(client, sender, receiver, 10_000, "enrich-analytics-1")

        r = client.get(
            f"/api/v1/analytics/accounts/{sender['account_id']}/ledger",
            headers={"X-Analytics-Key": ANALYTICS_KEY},
        )
        assert r.status_code == 200, r.text
        debit = next(e for e in r.json() if e["entry_type"] == "DEBIT")
        assert debit["transaction_type"] == "TRANSFER"
        assert debit["counterparty_account_id"] == receiver["account_id"]


# ═══════════════════════════════════════════════════════════════════════════════
# 5. start_date/end_date 필터 — /transactions, /analytics/.../ledger
# ═══════════════════════════════════════════════════════════════════════════════


class TestLedgerDateRangeFilter:
    def test_future_start_date_excludes_todays_entries(self, client):
        acct = _make_account(client, "DateFilter", 10_000)
        tomorrow = (_today_utc() + timedelta(days=1)).isoformat()

        r = client.get(
            f"/api/v1/accounts/{acct['account_id']}/transactions",
            params={"start_date": tomorrow},
        )
        assert r.status_code == 200, r.text
        assert r.json() == []

    def test_today_range_includes_entries(self, client):
        acct = _make_account(client, "DateFilterToday", 10_000)
        today = _today_utc().isoformat()

        r = client.get(
            f"/api/v1/accounts/{acct['account_id']}/transactions",
            params={"start_date": today, "end_date": today},
        )
        assert r.status_code == 200, r.text
        assert len(r.json()) == 1

    def test_analytics_ledger_date_range_filter(self, client):
        acct = _make_account(client, "DateFilterAnalytics", 10_000)
        yesterday = (_today_utc() - timedelta(days=1)).isoformat()

        r = client.get(
            f"/api/v1/analytics/accounts/{acct['account_id']}/ledger",
            params={"end_date": yesterday},
            headers={"X-Analytics-Key": ANALYTICS_KEY},
        )
        assert r.status_code == 200, r.text
        assert r.json() == []


# ═══════════════════════════════════════════════════════════════════════════════
# 6. GET /analytics/accounts/{id}/transfers/daily-total
# ═══════════════════════════════════════════════════════════════════════════════


class TestDailyTransferredTotal:
    def test_excludes_seed_deposit_counts_real_transfers_only(self, client):
        sender = _make_account(client, "DailyTotalSender", 100_000)
        receiver = _make_account(client, "DailyTotalReceiver", 0)
        _transfer(client, sender, receiver, 30_000, "daily-total-1")
        _transfer(client, sender, receiver, 20_000, "daily-total-2")

        r = client.get(
            f"/api/v1/analytics/accounts/{sender['account_id']}/transfers/daily-total",
            headers={"X-Analytics-Key": ANALYTICS_KEY},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total_sent"] == 50_000  # 100_000 초기입금은 제외
        assert body["business_date"] == _today_utc().isoformat()

    def test_receiver_side_not_counted(self, client):
        sender = _make_account(client, "DailyTotalSender2", 100_000)
        receiver = _make_account(client, "DailyTotalReceiver2", 0)
        _transfer(client, sender, receiver, 30_000, "daily-total-3")

        r = client.get(
            f"/api/v1/analytics/accounts/{receiver['account_id']}/transfers/daily-total",
            headers={"X-Analytics-Key": ANALYTICS_KEY},
        )
        assert r.json()["total_sent"] == 0

    def test_explicit_business_date_with_no_activity_returns_zero(self, client):
        acct = _make_account(client, "DailyTotalNoActivity", 10_000)
        past_date = (_today_utc() - timedelta(days=30)).isoformat()

        r = client.get(
            f"/api/v1/analytics/accounts/{acct['account_id']}/transfers/daily-total",
            params={"business_date": past_date},
            headers={"X-Analytics-Key": ANALYTICS_KEY},
        )
        assert r.json()["total_sent"] == 0

    def test_requires_analytics_key(self, client):
        acct = _make_account(client, "DailyTotalNoKey", 10_000)
        r = client.get(
            f"/api/v1/analytics/accounts/{acct['account_id']}/transfers/daily-total"
        )
        assert r.status_code == 401

    def test_unknown_account_404(self, client):
        r = client.get(
            "/api/v1/analytics/accounts/does-not-exist/transfers/daily-total",
            headers={"X-Analytics-Key": ANALYTICS_KEY},
        )
        assert r.status_code == 404
