"""
Independent test for Sub-AC 4:
  GET /accounts/{id}/transactions — 200, schema validation,
  covers transaction_id / amount / entry_type / created_at / running_balance.
"""
import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_account(client, owner: str = "TxUser", initial_balance: int = 100_000) -> dict:
    r = client.post("/api/v1/accounts", json={"owner": owner, "initial_balance": initial_balance})
    assert r.status_code == 201, r.text
    return r.json()


def _do_transfer(client, sender_id: str, receiver_id: str, amount: int, key: str) -> dict:
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


# ═══════════════════════════════════════════════════════════════════════════════
# Schema validation tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetTransactionsSchema:
    """Sub-AC 4: response body schema contract."""

    REQUIRED_FIELDS = {"entry_id", "transaction_id", "entry_type", "amount", "running_balance", "created_at"}

    def test_200_status(self, client):
        acct = _make_account(client, "SchemaUser", 10_000)
        r = client.get(f"/api/v1/accounts/{acct['account_id']}/transactions")
        assert r.status_code == 200

    def test_returns_list(self, client):
        acct = _make_account(client, "ListUser", 10_000)
        body = client.get(f"/api/v1/accounts/{acct['account_id']}/transactions").json()
        assert isinstance(body, list)

    def test_initial_deposit_creates_one_credit_entry(self, client):
        acct = _make_account(client, "DepositUser", 50_000)
        body = client.get(f"/api/v1/accounts/{acct['account_id']}/transactions").json()
        assert len(body) == 1
        entry = body[0]
        assert entry["entry_type"] == "CREDIT"
        assert entry["amount"] == 50_000

    def test_all_required_fields_present(self, client):
        acct = _make_account(client, "FieldUser", 20_000)
        body = client.get(f"/api/v1/accounts/{acct['account_id']}/transactions").json()
        assert len(body) >= 1
        for entry in body:
            missing = self.REQUIRED_FIELDS - set(entry.keys())
            assert not missing, f"Missing fields: {missing}"

    def test_field_types(self, client):
        acct = _make_account(client, "TypeUser", 30_000)
        body = client.get(f"/api/v1/accounts/{acct['account_id']}/transactions").json()
        assert len(body) >= 1
        entry = body[0]
        assert isinstance(entry["entry_id"], str)
        assert isinstance(entry["transaction_id"], str)
        assert isinstance(entry["entry_type"], str)
        assert isinstance(entry["amount"], int)
        assert isinstance(entry["running_balance"], int)
        assert isinstance(entry["created_at"], str)  # ISO-8601 string

    def test_amount_is_positive_integer(self, client):
        acct = _make_account(client, "PosUser", 77_000)
        body = client.get(f"/api/v1/accounts/{acct['account_id']}/transactions").json()
        for entry in body:
            assert entry["amount"] > 0, "amount must always be positive"

    def test_entry_type_enum_values(self, client):
        acct = _make_account(client, "EnumUser", 10_000)
        body = client.get(f"/api/v1/accounts/{acct['account_id']}/transactions").json()
        valid_types = {"CREDIT", "DEBIT"}
        for entry in body:
            assert entry["entry_type"] in valid_types


# ═══════════════════════════════════════════════════════════════════════════════
# Functional / content tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetTransactionsContent:
    """Sub-AC 4: entries reflect actual transfer history."""

    def test_zero_balance_account_has_no_entries(self, client):
        acct = _make_account(client, "ZeroUser", 0)
        body = client.get(f"/api/v1/accounts/{acct['account_id']}/transactions").json()
        assert body == []

    def test_debit_entry_after_transfer_sent(self, client):
        sender = _make_account(client, "SenderTx", 200_000)
        receiver = _make_account(client, "ReceiverTx", 0)
        _do_transfer(client, sender["account_id"], receiver["account_id"], 50_000, "tx-schema-001")

        entries = client.get(f"/api/v1/accounts/{sender['account_id']}/transactions").json()
        types = [e["entry_type"] for e in entries]
        assert "DEBIT" in types, f"Expected DEBIT in sender entries: {types}"

    def test_credit_entry_after_transfer_received(self, client):
        sender = _make_account(client, "SenderTx2", 200_000)
        receiver = _make_account(client, "ReceiverTx2", 0)
        _do_transfer(client, sender["account_id"], receiver["account_id"], 50_000, "tx-schema-002")

        entries = client.get(f"/api/v1/accounts/{receiver['account_id']}/transactions").json()
        types = [e["entry_type"] for e in entries]
        assert "CREDIT" in types, f"Expected CREDIT in receiver entries: {types}"

    def test_debit_amount_matches_transfer(self, client):
        sender = _make_account(client, "AmtSender", 300_000)
        receiver = _make_account(client, "AmtReceiver", 0)
        transfer_amount = 75_000
        _do_transfer(client, sender["account_id"], receiver["account_id"], transfer_amount, "tx-amt-001")

        entries = client.get(f"/api/v1/accounts/{sender['account_id']}/transactions").json()
        debit_entries = [e for e in entries if e["entry_type"] == "DEBIT"]
        assert len(debit_entries) >= 1
        assert debit_entries[0]["amount"] == transfer_amount

    def test_running_balance_after_debit(self, client):
        initial = 100_000
        transfer_amount = 30_000
        sender = _make_account(client, "RunBalSender", initial)
        receiver = _make_account(client, "RunBalReceiver", 0)
        _do_transfer(client, sender["account_id"], receiver["account_id"], transfer_amount, "tx-runbal-001")

        entries = client.get(f"/api/v1/accounts/{sender['account_id']}/transactions").json()
        debit_entries = [e for e in entries if e["entry_type"] == "DEBIT"]
        assert debit_entries[0]["running_balance"] == initial - transfer_amount

    def test_transaction_id_links_entries(self, client):
        """Debit + credit entries for same transfer share transaction_id."""
        sender = _make_account(client, "LinkSender", 200_000)
        receiver = _make_account(client, "LinkReceiver", 0)
        txn = _do_transfer(client, sender["account_id"], receiver["account_id"], 10_000, "tx-link-001")
        txn_id = txn["transfer_id"]

        s_entries = client.get(f"/api/v1/accounts/{sender['account_id']}/transactions").json()
        r_entries = client.get(f"/api/v1/accounts/{receiver['account_id']}/transactions").json()

        s_txn_ids = {e["transaction_id"] for e in s_entries}
        r_txn_ids = {e["transaction_id"] for e in r_entries}
        assert txn_id in s_txn_ids
        assert txn_id in r_txn_ids


# ═══════════════════════════════════════════════════════════════════════════════
# Pagination / edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetTransactionsPagination:
    """Sub-AC 4: pagination params, 404 for missing account."""

    def test_limit_param(self, client):
        acct = _make_account(client, "LimitUser", 10_000)
        r = client.get(f"/api/v1/accounts/{acct['account_id']}/transactions?limit=1")
        assert r.status_code == 200
        body = r.json()
        assert len(body) <= 1

    def test_offset_param(self, client):
        acct = _make_account(client, "OffsetUser", 10_000)
        r = client.get(f"/api/v1/accounts/{acct['account_id']}/transactions?offset=999")
        assert r.status_code == 200
        assert r.json() == []

    def test_not_found_returns_404_and_error_schema(self, client):
        r = client.get("/api/v1/accounts/00000000-0000-0000-0000-000000000000/transactions")
        assert r.status_code == 404
        body = r.json()
        assert body["error_code"] == "ACCOUNT_NOT_FOUND"
        assert "message" in body
