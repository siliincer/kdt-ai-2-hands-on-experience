"""
AC: 이중기입 원장 원자성 + 잔액보존 검증

- DEBIT/CREDIT pair recorded in single DB transaction
- Failure → full rollback (no partial ledger entries)
- Post-commit: sender.balance + receiver.balance == pre-transfer total
"""

from sqlalchemy import text

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_account(client, owner: str, initial_balance: int = 0) -> dict:
    r = client.post(
        "/api/v1/accounts", json={"owner": owner, "initial_balance": initial_balance}
    )
    assert r.status_code == 201, r.text
    return r.json()


def _balance(client, account_id: str) -> int:
    r = client.get(f"/api/v1/accounts/{account_id}/balance")
    assert r.status_code == 200
    return r.json()["balance"]


def _transfer(client, sender: dict, receiver: dict, amount: int, key: str):
    return client.post(
        "/api/v1/transfers",
        json={
            "sender_account_number": sender["account_number"],
            "receiver_bank_name": receiver["bank_name"],
            "receiver_account_number": receiver["account_number"],
            "amount": amount,
        },
        headers={"Idempotency-Key": key},
    )


def _ledger_entries(db_engine, account_id: str) -> list:
    with db_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT entry_id, entry_type, amount FROM ledger_entries "
                "WHERE account_id = :aid ORDER BY rowid"
            ),
            {"aid": account_id},
        ).fetchall()
    return rows


# ═══════════════════════════════════════════════════════════════════════════════
# Balance preservation (runtime assert path)
# ═══════════════════════════════════════════════════════════════════════════════


class TestBalancePreservation:
    """Post-commit: sender.balance + receiver.balance == pre-transfer total."""

    def test_total_preserved_single_transfer(self, client):
        sender = _make_account(client, "BP_S1", 300_000)
        receiver = _make_account(client, "BP_R1", 50_000)

        pre_total = 300_000 + 50_000

        r = _transfer(client, sender, receiver, 100_000, "bp-001")
        assert r.status_code == 200

        post_total = _balance(client, sender["account_id"]) + _balance(
            client, receiver["account_id"]
        )
        assert post_total == pre_total, (
            f"Balance leaked: pre={pre_total}, post={post_total}"
        )

    def test_total_preserved_multiple_transfers(self, client):
        """Multiple sequential transfers: sum invariant holds after each."""
        a = _make_account(client, "BP_A", 500_000)
        b = _make_account(client, "BP_B", 200_000)
        c = _make_account(client, "BP_C", 100_000)

        pre_total = 500_000 + 200_000 + 100_000

        _transfer(client, a, b, 50_000, "bp-multi-001")
        _transfer(client, b, c, 30_000, "bp-multi-002")
        _transfer(client, c, a, 10_000, "bp-multi-003")

        post_total = (
            _balance(client, a["account_id"])
            + _balance(client, b["account_id"])
            + _balance(client, c["account_id"])
        )
        assert post_total == pre_total

    def test_sender_decremented_exactly(self, client):
        sender = _make_account(client, "Exact_S", 400_000)
        receiver = _make_account(client, "Exact_R", 0)
        amount = 123_456

        _transfer(client, sender, receiver, amount, "exact-001")

        assert _balance(client, sender["account_id"]) == 400_000 - amount
        assert _balance(client, receiver["account_id"]) == amount

    def test_no_balance_change_on_failed_transfer(self, client):
        """Insufficient balance: balances unchanged, no partial ledger."""
        sender = _make_account(client, "Fail_S", 1_000)
        receiver = _make_account(client, "Fail_R", 0)

        r = _transfer(client, sender, receiver, 999_999, "fail-001")
        assert r.status_code == 422

        assert _balance(client, sender["account_id"]) == 1_000
        assert _balance(client, receiver["account_id"]) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Double-entry ledger pair atomicity
# ═══════════════════════════════════════════════════════════════════════════════


class TestDoubleEntryAtomicity:
    """DEBIT and CREDIT entries must be written together or not at all."""

    def test_both_debit_and_credit_entries_created(self, client, db_engine):
        sender = _make_account(client, "DE_S1", 200_000)
        receiver = _make_account(client, "DE_R1", 0)
        amount = 75_000

        r = _transfer(client, sender, receiver, amount, "de-pair-001")
        assert r.status_code == 200
        txn_id = r.json()["transfer_id"]

        with db_engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT account_id, entry_type, amount FROM ledger_entries "
                    "WHERE transaction_id = :tid ORDER BY entry_type"
                ),
                {"tid": txn_id},
            ).fetchall()

        assert len(rows) == 2, f"Expected 2 ledger entries, got {len(rows)}"
        types = {row[1] for row in rows}
        assert "DEBIT" in types, "DEBIT entry missing"
        assert "CREDIT" in types, "CREDIT entry missing"

    def test_debit_entry_belongs_to_sender(self, client, db_engine):
        sender = _make_account(client, "DE_S2", 100_000)
        receiver = _make_account(client, "DE_R2", 0)

        r = _transfer(client, sender, receiver, 10_000, "de-debit-001")
        txn_id = r.json()["transfer_id"]

        with db_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT account_id FROM ledger_entries "
                    "WHERE transaction_id = :tid AND entry_type = 'DEBIT'"
                ),
                {"tid": txn_id},
            ).fetchone()

        assert row is not None
        assert row[0] == sender["account_id"]

    def test_credit_entry_belongs_to_receiver(self, client, db_engine):
        sender = _make_account(client, "DE_S3", 100_000)
        receiver = _make_account(client, "DE_R3", 0)

        r = _transfer(
            client,
            sender,
            receiver,
            10_000,
            "de-credit-001",
        )
        txn_id = r.json()["transfer_id"]

        with db_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT account_id FROM ledger_entries "
                    "WHERE transaction_id = :tid AND entry_type = 'CREDIT'"
                ),
                {"tid": txn_id},
            ).fetchone()

        assert row is not None
        assert row[0] == receiver["account_id"]

    def test_debit_credit_amounts_equal(self, client, db_engine):
        """DEBIT amount == CREDIT amount for same transaction."""
        sender = _make_account(client, "DE_S4", 500_000)
        receiver = _make_account(client, "DE_R4", 0)
        amount = 88_888

        r = _transfer(client, sender, receiver, amount, "de-eq-001")
        txn_id = r.json()["transfer_id"]

        with db_engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT entry_type, amount FROM ledger_entries "
                    "WHERE transaction_id = :tid"
                ),
                {"tid": txn_id},
            ).fetchall()

        amounts = {row[0]: row[1] for row in rows}
        assert amounts["DEBIT"] == amount
        assert amounts["CREDIT"] == amount

    def test_failed_transfer_leaves_no_ledger_entries(self, client, db_engine):
        """On validation failure, no ledger entries written (full rollback)."""
        sender = _make_account(client, "DE_Fail", 500)
        receiver = _make_account(client, "DE_FailR", 0)

        r = _transfer(client, sender, receiver, 999_999, "de-fail-001")
        assert r.status_code == 422

        with db_engine.connect() as conn:
            # Count ledger entries: sender should have only the initial CREDIT (seed)
            count = conn.execute(
                text(
                    "SELECT COUNT(*) FROM ledger_entries "
                    "WHERE account_id = :aid AND entry_type = 'DEBIT'"
                ),
                {"aid": sender["account_id"]},
            ).scalar()

        assert count == 0, (
            f"No DEBIT entries expected after failed transfer, got {count}"
        )
