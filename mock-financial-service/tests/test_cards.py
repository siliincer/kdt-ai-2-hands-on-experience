"""Card entity tests — POST /cards, charges, settlement, analytics ledger."""

ANALYTICS_KEY = "analytics-demo-key"


# ── helpers ───────────────────────────────────────────────────────────────────


def _create_account(client, owner="alice", initial_balance=100_000):
    r = client.post("/api/v1/accounts", json={"owner": owner, "initial_balance": initial_balance})
    assert r.status_code == 201
    return r.json()


def _create_card(client, account_id, limit=50_000, currency="KRW"):
    r = client.post(
        "/api/v1/cards",
        json={"account_id": account_id, "limit": limit, "currency": currency},
    )
    return r


def _charge(client, card_id, amount, idem_key):
    return client.post(
        f"/api/v1/cards/{card_id}/charges",
        json={"amount": amount},
        headers={"Idempotency-Key": idem_key},
    )


def _settle(client, card_id):
    return client.post(f"/api/v1/cards/{card_id}/settle")


def _analytics_ledger(client, card_id):
    return client.get(
        f"/api/v1/analytics/cards/{card_id}/ledger",
        headers={"X-Analytics-Key": ANALYTICS_KEY},
    )


# ── AC 1: POST /api/v1/cards ──────────────────────────────────────────────────


class TestCreateCard:
    def test_create_card_success(self, client):
        acct = _create_account(client)
        r = _create_card(client, acct["account_id"], limit=30_000)
        assert r.status_code == 201
        body = r.json()
        assert body["account_id"] == acct["account_id"]
        assert body["limit"] == 30_000
        assert body["currency"] == "KRW"
        assert "card_id" in body
        assert "created_at" in body

    def test_create_card_unknown_account(self, client):
        r = _create_card(client, "nonexistent-account-id", limit=10_000)
        assert r.status_code == 404
        assert r.json()["error_code"] == "ACCOUNT_NOT_FOUND"

    def test_create_card_invalid_limit(self, client):
        acct = _create_account(client)
        r = client.post("/api/v1/cards", json={"account_id": acct["account_id"], "limit": 0})
        assert r.status_code == 422

    def test_create_multiple_cards_same_account(self, client):
        acct = _create_account(client)
        r1 = _create_card(client, acct["account_id"], limit=10_000)
        r2 = _create_card(client, acct["account_id"], limit=20_000)
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["card_id"] != r2.json()["card_id"]

    def test_get_card(self, client):
        acct = _create_account(client)
        card = _create_card(client, acct["account_id"], limit=15_000).json()
        r = client.get(f"/api/v1/cards/{card['card_id']}")
        assert r.status_code == 200
        assert r.json()["card_id"] == card["card_id"]
        assert r.json()["limit"] == 15_000

    def test_get_card_not_found(self, client):
        r = client.get("/api/v1/cards/nonexistent")
        assert r.status_code == 404
        assert r.json()["error_code"] == "CARD_NOT_FOUND"


# ── Charge tests ──────────────────────────────────────────────────────────────


class TestCardCharge:
    def test_charge_success(self, client):
        acct = _create_account(client)
        card = _create_card(client, acct["account_id"], limit=50_000).json()
        r = _charge(client, card["card_id"], 10_000, "idem-001")
        assert r.status_code == 201
        body = r.json()
        assert body["card_id"] == card["card_id"]
        assert body["amount"] == 10_000
        assert "card_ledger_entry_id" in body

    def test_charge_account_balance_untouched(self, client):
        """Card purchase must NOT touch account balance until settlement."""
        acct = _create_account(client, initial_balance=100_000)
        card = _create_card(client, acct["account_id"], limit=50_000).json()
        _charge(client, card["card_id"], 20_000, "idem-002")
        balance_r = client.get(f"/api/v1/accounts/{acct['account_id']}/balance")
        assert balance_r.json()["balance"] == 100_000  # unchanged

    def test_charge_limit_exceeded(self, client):
        acct = _create_account(client, initial_balance=200_000)
        card = _create_card(client, acct["account_id"], limit=30_000).json()
        _charge(client, card["card_id"], 20_000, "idem-a1")
        r = _charge(client, card["card_id"], 15_000, "idem-a2")  # 20k+15k > 30k
        assert r.status_code == 422
        assert r.json()["error_code"] == "CARD_LIMIT_EXCEEDED"

    def test_charge_exact_limit(self, client):
        acct = _create_account(client, initial_balance=50_000)
        card = _create_card(client, acct["account_id"], limit=30_000).json()
        r = _charge(client, card["card_id"], 30_000, "idem-exact")
        assert r.status_code == 201

    def test_charge_missing_idempotency_key(self, client):
        acct = _create_account(client)
        card = _create_card(client, acct["account_id"], limit=10_000).json()
        r = client.post(f"/api/v1/cards/{card['card_id']}/charges", json={"amount": 5_000})
        assert r.status_code == 422
        assert r.json()["error_code"] == "MISSING_IDEMPOTENCY_KEY"

    def test_charge_idempotency_replay(self, client):
        acct = _create_account(client, initial_balance=50_000)
        card = _create_card(client, acct["account_id"], limit=50_000).json()
        r1 = _charge(client, card["card_id"], 10_000, "same-key")
        r2 = _charge(client, card["card_id"], 10_000, "same-key")
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["card_ledger_entry_id"] == r2.json()["card_ledger_entry_id"]

    def test_charge_card_not_found(self, client):
        r = _charge(client, "nonexistent-card", 5_000, "idem-nf")
        assert r.status_code == 404
        assert r.json()["error_code"] == "CARD_NOT_FOUND"


# ── Settlement tests ──────────────────────────────────────────────────────────


class TestCardSettlement:
    def test_settle_debits_account(self, client):
        acct = _create_account(client, initial_balance=100_000)
        card = _create_card(client, acct["account_id"], limit=50_000).json()
        _charge(client, card["card_id"], 20_000, "idem-s1")
        _charge(client, card["card_id"], 10_000, "idem-s2")

        r = _settle(client, card["card_id"])
        assert r.status_code == 200
        body = r.json()
        assert body["card_id"] == card["card_id"]
        assert body["settled_amount"] == 30_000
        assert body["status"] == "success"
        assert "settlement_watermark_rowid" in body

        # Account balance must decrease by settled amount
        balance_r = client.get(f"/api/v1/accounts/{acct['account_id']}/balance")
        assert balance_r.json()["balance"] == 70_000

    def test_settle_resets_available_limit(self, client):
        """After settlement, limit available again for new charges."""
        acct = _create_account(client, initial_balance=200_000)
        card = _create_card(client, acct["account_id"], limit=30_000).json()
        _charge(client, card["card_id"], 30_000, "idem-r1")

        # Can't charge more — limit hit
        r = _charge(client, card["card_id"], 1_000, "idem-r2")
        assert r.status_code == 422

        # Settle
        _settle(client, card["card_id"])

        # Now can charge again up to limit
        r2 = _charge(client, card["card_id"], 25_000, "idem-r3")
        assert r2.status_code == 201

    def test_settle_nothing_to_settle(self, client):
        acct = _create_account(client, initial_balance=50_000)
        card = _create_card(client, acct["account_id"], limit=20_000).json()
        r = _settle(client, card["card_id"])
        assert r.status_code == 422
        assert r.json()["error_code"] == "NOTHING_TO_SETTLE"

    def test_settle_twice_only_settles_new_charges(self, client):
        acct = _create_account(client, initial_balance=200_000)
        card = _create_card(client, acct["account_id"], limit=50_000).json()
        _charge(client, card["card_id"], 10_000, "idem-t1")
        _settle(client, card["card_id"])

        # Second settle with no new charges
        r = _settle(client, card["card_id"])
        assert r.status_code == 422
        assert r.json()["error_code"] == "NOTHING_TO_SETTLE"

    def test_settle_only_new_charges_after_first_settlement(self, client):
        acct = _create_account(client, initial_balance=200_000)
        card = _create_card(client, acct["account_id"], limit=50_000).json()
        _charge(client, card["card_id"], 10_000, "idem-u1")
        _settle(client, card["card_id"])  # settles 10k, balance=190k

        _charge(client, card["card_id"], 5_000, "idem-u2")
        r = _settle(client, card["card_id"])
        assert r.status_code == 200
        assert r.json()["settled_amount"] == 5_000  # only new charge

        balance_r = client.get(f"/api/v1/accounts/{acct['account_id']}/balance")
        assert balance_r.json()["balance"] == 185_000

    def test_settle_insufficient_balance(self, client):
        acct = _create_account(client, initial_balance=5_000)
        card = _create_card(client, acct["account_id"], limit=50_000).json()
        # Bypass normal limit by charging using a different card with high limit
        # Instead, just directly charge more than account balance
        # (card limit is higher than account balance)
        _charge(client, card["card_id"], 10_000, "idem-insuf")  # limit=50k, charge=10k OK
        r = _settle(client, card["card_id"])  # account only has 5k
        assert r.status_code == 422
        assert r.json()["error_code"] == "INSUFFICIENT_BALANCE"

    def test_settle_card_not_found(self, client):
        r = _settle(client, "nonexistent-card")
        assert r.status_code == 404
        assert r.json()["error_code"] == "CARD_NOT_FOUND"


# ── Analytics ledger tests ────────────────────────────────────────────────────


class TestCardAnalytics:
    def test_analytics_ledger_requires_key(self, client):
        acct = _create_account(client)
        card = _create_card(client, acct["account_id"], limit=10_000).json()
        r = client.get(f"/api/v1/analytics/cards/{card['card_id']}/ledger")
        assert r.status_code == 401

    def test_analytics_ledger_empty(self, client):
        acct = _create_account(client)
        card = _create_card(client, acct["account_id"], limit=10_000).json()
        r = _analytics_ledger(client, card["card_id"])
        assert r.status_code == 200
        assert r.json() == []

    def test_analytics_ledger_returns_entries(self, client):
        acct = _create_account(client, initial_balance=100_000)
        card = _create_card(client, acct["account_id"], limit=50_000).json()
        _charge(client, card["card_id"], 5_000, "idem-al1")
        _charge(client, card["card_id"], 8_000, "idem-al2")
        r = _analytics_ledger(client, card["card_id"])
        assert r.status_code == 200
        entries = r.json()
        assert len(entries) == 2
        amounts = {e["amount"] for e in entries}
        assert amounts == {5_000, 8_000}

    def test_analytics_ledger_card_not_found(self, client):
        r = client.get(
            "/api/v1/analytics/cards/nonexistent/ledger",
            headers={"X-Analytics-Key": ANALYTICS_KEY},
        )
        assert r.status_code == 404
        assert r.json()["error_code"] == "CARD_NOT_FOUND"

    def test_analytics_card_detail(self, client):
        acct = _create_account(client)
        card = _create_card(client, acct["account_id"], limit=25_000).json()
        r = client.get(
            f"/api/v1/analytics/cards/{card['card_id']}",
            headers={"X-Analytics-Key": ANALYTICS_KEY},
        )
        assert r.status_code == 200
        assert r.json()["limit"] == 25_000
        assert r.json()["card_id"] == card["card_id"]

    def test_analytics_wrong_key(self, client):
        acct = _create_account(client)
        card = _create_card(client, acct["account_id"], limit=10_000).json()
        r = client.get(
            f"/api/v1/analytics/cards/{card['card_id']}/ledger",
            headers={"X-Analytics-Key": "wrong-key"},
        )
        assert r.status_code == 401


# ── Watermark isolation: unsettled predicate ──────────────────────────────────


class TestWatermarkPredicate:
    """Canonical unsettled predicate: rowid > watermark (exclusive lower bound)."""

    def test_limit_check_uses_watermark(self, client):
        """Limit check sums only entries after watermark, not all entries."""
        acct = _create_account(client, initial_balance=500_000)
        card = _create_card(client, acct["account_id"], limit=30_000).json()

        # Charge and settle twice, each time confirming post-settle limit resets
        _charge(client, card["card_id"], 30_000, "wm-c1")
        _settle(client, card["card_id"])  # watermark moves past first charge

        _charge(client, card["card_id"], 30_000, "wm-c2")
        _settle(client, card["card_id"])  # watermark moves past second charge

        # Third charge up to limit must be accepted (not blocked by old settled entries)
        r = _charge(client, card["card_id"], 30_000, "wm-c3")
        assert r.status_code == 201
