"""
Independent test for Sub-AC 5:
  POST /transfers — 200 response, schema fields transfer_id / from_account /
  to_account / amount / status validated.
"""


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_account(client, owner: str, initial_balance: int = 0) -> dict:
    r = client.post(
        "/api/v1/accounts", json={"owner": owner, "initial_balance": initial_balance}
    )
    assert r.status_code == 201, r.text
    return r.json()


def _transfer(client, sender_id: str, receiver_id: str, amount: int, key: str):
    return client.post(
        "/api/v1/transfers",
        json={
            "sender_account_id": sender_id,
            "receiver_account_id": receiver_id,
            "amount": amount,
        },
        headers={"Idempotency-Key": key},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Sub-AC 5: POST /transfers — 200 + schema contract
# ═══════════════════════════════════════════════════════════════════════════════


class TestTransferAPI:
    """Verify POST /transfers returns 200 and mandated schema fields."""

    REQUIRED_FIELDS = {"transfer_id", "from_account", "to_account", "amount", "status"}

    def test_200_status_code(self, client):
        """Endpoint must respond with HTTP 200."""
        sender = _make_account(client, "T5Sender", 100_000)
        receiver = _make_account(client, "T5Receiver", 0)
        r = _transfer(
            client,
            sender["account_id"],
            receiver["account_id"],
            10_000,
            "t5-status-001",
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_schema_required_fields_present(self, client):
        """Response body must contain all mandated schema fields."""
        sender = _make_account(client, "T5SchemaS", 200_000)
        receiver = _make_account(client, "T5SchemaR", 0)
        r = _transfer(
            client,
            sender["account_id"],
            receiver["account_id"],
            50_000,
            "t5-schema-001",
        )
        assert r.status_code == 200
        body = r.json()
        missing = self.REQUIRED_FIELDS - set(body.keys())
        assert not missing, f"Missing schema fields: {missing}"

    def test_transfer_id_is_string(self, client):
        """transfer_id must be a non-empty string (UUID)."""
        sender = _make_account(client, "T5IdS", 100_000)
        receiver = _make_account(client, "T5IdR", 0)
        r = _transfer(
            client, sender["account_id"], receiver["account_id"], 1_000, "t5-id-001"
        )
        body = r.json()
        assert isinstance(body["transfer_id"], str)
        assert len(body["transfer_id"]) > 0

    def test_from_account_matches_sender(self, client):
        """from_account must equal the sender's account_id."""
        sender = _make_account(client, "T5FromS", 100_000)
        receiver = _make_account(client, "T5FromR", 0)
        r = _transfer(
            client, sender["account_id"], receiver["account_id"], 1_000, "t5-from-001"
        )
        body = r.json()
        assert body["from_account"] == sender["account_id"]

    def test_to_account_matches_receiver(self, client):
        """to_account must equal the receiver's account_id."""
        sender = _make_account(client, "T5ToS", 100_000)
        receiver = _make_account(client, "T5ToR", 0)
        r = _transfer(
            client, sender["account_id"], receiver["account_id"], 1_000, "t5-to-001"
        )
        body = r.json()
        assert body["to_account"] == receiver["account_id"]

    def test_amount_matches_request(self, client):
        """amount in response must equal requested transfer amount."""
        sender = _make_account(client, "T5AmtS", 300_000)
        receiver = _make_account(client, "T5AmtR", 0)
        r = _transfer(
            client, sender["account_id"], receiver["account_id"], 77_000, "t5-amt-001"
        )
        body = r.json()
        assert body["amount"] == 77_000

    def test_amount_is_integer(self, client):
        """amount must be an integer (no float, no rounding error)."""
        sender = _make_account(client, "T5IntS", 100_000)
        receiver = _make_account(client, "T5IntR", 0)
        r = _transfer(
            client, sender["account_id"], receiver["account_id"], 3_000, "t5-int-001"
        )
        body = r.json()
        assert isinstance(body["amount"], int)

    def test_status_is_success(self, client):
        """status must be 'success' for a valid transfer."""
        sender = _make_account(client, "T5StatS", 100_000)
        receiver = _make_account(client, "T5StatR", 0)
        r = _transfer(
            client, sender["account_id"], receiver["account_id"], 5_000, "t5-stat-001"
        )
        body = r.json()
        assert body["status"] == "success"

    def test_no_extra_required_fields_block_response(self, client):
        """Response must include all 5 schema fields simultaneously."""
        sender = _make_account(client, "T5AllS", 500_000)
        receiver = _make_account(client, "T5AllR", 0)
        r = _transfer(
            client, sender["account_id"], receiver["account_id"], 123_000, "t5-all-001"
        )
        assert r.status_code == 200
        body = r.json()
        assert body["transfer_id"]
        assert body["from_account"] == sender["account_id"]
        assert body["to_account"] == receiver["account_id"]
        assert body["amount"] == 123_000
        assert body["status"] == "success"
