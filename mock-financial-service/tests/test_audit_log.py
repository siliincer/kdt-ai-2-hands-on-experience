"""
Sub-AC 5a: AuditLog 모델 및 append-only 기록 로직 검증

- 송금 성공 시 AuditLog INSERT
- 송금 실패(잔액초과/없는계좌/자기송금/키충돌) 시 AuditLog INSERT
- 계좌생성 시 AuditLog INSERT
- 누락 케이스: 감사로그 존재 확인 (not missing)
"""
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from financial_service.models import AuditLog


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_account(client, owner: str, initial_balance: int = 0) -> dict:
    r = client.post("/api/v1/accounts", json={"owner": owner, "initial_balance": initial_balance})
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


def _audit_rows(db_engine, *, action: str | None = None, status: str | None = None) -> list:
    """Fetch audit_log rows, optionally filtered by action and/or status."""
    query = "SELECT audit_log_id, action, status, transaction_id, actor FROM audit_logs WHERE 1=1"
    params: dict = {}
    if action:
        query += " AND action = :action"
        params["action"] = action
    if status:
        query += " AND status = :status"
        params["status"] = status
    with db_engine.connect() as conn:
        return conn.execute(text(query), params).fetchall()


# ═══════════════════════════════════════════════════════════════════════════════
# AuditLog on account creation
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditLogAccountCreate:
    def test_account_create_writes_audit(self, client, db_engine):
        """계좌생성 시 ACCOUNT_CREATE 감사로그 생성."""
        _make_account(client, "AuditOwner1", 10_000)

        rows = _audit_rows(db_engine, action="ACCOUNT_CREATE", status="success")
        assert len(rows) >= 1, "AuditLog missing for account creation"

    def test_account_create_audit_actor(self, client, db_engine):
        """감사로그 actor == account owner."""
        owner = "AuditActorOwner"
        _make_account(client, owner, 5_000)

        with db_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT actor FROM audit_logs WHERE action = 'ACCOUNT_CREATE' AND actor = :actor"
                ),
                {"actor": owner},
            ).fetchone()
        assert row is not None, f"No audit log found with actor={owner}"
        assert row[0] == owner


# ═══════════════════════════════════════════════════════════════════════════════
# AuditLog on successful transfer
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditLogTransferSuccess:
    def test_success_transfer_writes_audit(self, client, db_engine):
        """성공 송금 → status=success AuditLog 생성."""
        sender = _make_account(client, "AL_S1", 100_000)
        receiver = _make_account(client, "AL_R1", 0)

        r = _transfer(client, sender["account_id"], receiver["account_id"], 10_000, "al-success-001")
        assert r.status_code == 200
        txn_id = r.json()["transfer_id"]

        rows = _audit_rows(db_engine, action="TRANSFER", status="success")
        assert len(rows) >= 1, "No success AuditLog for successful transfer"

        # Verify the audit is linked to the transaction
        linked = [row for row in rows if row[3] == txn_id]
        assert len(linked) == 1, f"Expected 1 audit linked to txn {txn_id}, got {len(linked)}"

    def test_success_audit_actor_is_sender(self, client, db_engine):
        """성공 감사로그 actor == sender_account_id."""
        sender = _make_account(client, "AL_S2", 50_000)
        receiver = _make_account(client, "AL_R2", 0)

        r = _transfer(client, sender["account_id"], receiver["account_id"], 5_000, "al-actor-001")
        assert r.status_code == 200
        txn_id = r.json()["transfer_id"]

        with db_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT actor, transaction_id FROM audit_logs "
                    "WHERE action = 'TRANSFER' AND transaction_id = :tid"
                ),
                {"tid": txn_id},
            ).fetchone()

        assert row is not None, "Success audit log not found"
        assert row[0] == sender["account_id"], f"actor mismatch: {row[0]} != {sender['account_id']}"

    def test_success_audit_has_transaction_id(self, client, db_engine):
        """성공 감사로그는 transaction_id가 NULL이 아님."""
        sender = _make_account(client, "AL_S3", 50_000)
        receiver = _make_account(client, "AL_R3", 0)

        r = _transfer(client, sender["account_id"], receiver["account_id"], 1_000, "al-txnid-001")
        assert r.status_code == 200
        txn_id = r.json()["transfer_id"]

        with db_engine.connect() as conn:
            row = conn.execute(
                text("SELECT transaction_id FROM audit_logs WHERE transaction_id = :tid"),
                {"tid": txn_id},
            ).fetchone()

        assert row is not None
        assert row[0] is not None, "transaction_id is NULL in success audit"


# ═══════════════════════════════════════════════════════════════════════════════
# AuditLog on failed transfers (누락 케이스 포함)
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditLogTransferFailure:
    def test_insufficient_balance_writes_failure_audit(self, client, db_engine):
        """잔액초과 송금 실패 → status=failure AuditLog 생성 (누락 없음)."""
        sender = _make_account(client, "AL_InsufficientS", 1_000)
        receiver = _make_account(client, "AL_InsufficientR", 0)

        r = _transfer(client, sender["account_id"], receiver["account_id"], 999_999, "al-fail-insuf-001")
        assert r.status_code == 422

        rows = _audit_rows(db_engine, action="TRANSFER_FAILED", status="failure")
        assert len(rows) >= 1, "Failure AuditLog missing for insufficient balance transfer"

    def test_insufficient_balance_audit_contains_error_code(self, client, db_engine):
        """잔액초과 실패 감사로그 reason에 INSUFFICIENT_BALANCE 포함."""
        sender = _make_account(client, "AL_InsSender", 500)
        receiver = _make_account(client, "AL_InsReceiver", 0)

        _transfer(client, sender["account_id"], receiver["account_id"], 100_000, "al-fail-insuf-002")

        with db_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT reason, actor FROM audit_logs "
                    "WHERE action = 'TRANSFER_FAILED' AND actor = :actor "
                    "ORDER BY rowid DESC LIMIT 1"
                ),
                {"actor": sender["account_id"]},
            ).fetchone()

        assert row is not None, "Failure audit log not found"
        assert "INSUFFICIENT_BALANCE" in row[0], f"Expected INSUFFICIENT_BALANCE in reason, got: {row[0]}"

    def test_account_not_found_writes_failure_audit(self, client, db_engine):
        """없는계좌 송금 시도 → status=failure AuditLog 생성."""
        sender = _make_account(client, "AL_NFSender", 10_000)
        ghost_id = "00000000-0000-0000-0000-000000000000"

        r = _transfer(client, sender["account_id"], ghost_id, 1_000, "al-fail-nf-001")
        assert r.status_code == 404

        with db_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT reason FROM audit_logs "
                    "WHERE action = 'TRANSFER_FAILED' AND actor = :actor "
                    "ORDER BY rowid DESC LIMIT 1"
                ),
                {"actor": sender["account_id"]},
            ).fetchone()

        assert row is not None, "No failure audit for account-not-found transfer"
        assert "ACCOUNT_NOT_FOUND" in row[0], f"Expected ACCOUNT_NOT_FOUND in reason, got: {row[0]}"

    def test_self_transfer_writes_failure_audit(self, client, db_engine):
        """자기송금 시도 → status=failure AuditLog 생성."""
        acct = _make_account(client, "AL_SelfSender", 10_000)

        r = _transfer(client, acct["account_id"], acct["account_id"], 1_000, "al-fail-self-001")
        assert r.status_code == 422

        with db_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT reason FROM audit_logs "
                    "WHERE action = 'TRANSFER_FAILED' AND actor = :actor "
                    "ORDER BY rowid DESC LIMIT 1"
                ),
                {"actor": acct["account_id"]},
            ).fetchone()

        assert row is not None, "No failure audit for self-transfer"
        assert "SELF_TRANSFER" in row[0], f"Expected SELF_TRANSFER in reason, got: {row[0]}"

    def test_idempotency_conflict_writes_failure_audit(self, client, db_engine):
        """멱등성 키 충돌 → status=failure AuditLog 생성."""
        sender = _make_account(client, "AL_ConflictS", 100_000)
        receiver = _make_account(client, "AL_ConflictR", 0)
        other = _make_account(client, "AL_ConflictO", 0)

        # First transfer succeeds
        r1 = _transfer(client, sender["account_id"], receiver["account_id"], 1_000, "al-conflict-key-001")
        assert r1.status_code == 200

        # Same key, different payload → 409
        r2 = _transfer(client, sender["account_id"], other["account_id"], 2_000, "al-conflict-key-001")
        assert r2.status_code == 409

        with db_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT reason FROM audit_logs "
                    "WHERE action = 'TRANSFER_FAILED' AND actor = :actor "
                    "ORDER BY rowid DESC LIMIT 1"
                ),
                {"actor": sender["account_id"]},
            ).fetchone()

        assert row is not None, "No failure audit for idempotency conflict"
        assert "IDEMPOTENCY_CONFLICT" in row[0], f"Expected IDEMPOTENCY_CONFLICT in reason, got: {row[0]}"

    def test_failure_audit_transaction_id_is_null(self, client, db_engine):
        """실패 감사로그 transaction_id는 NULL (트랜잭션 미생성)."""
        sender = _make_account(client, "AL_NullTxnS", 100)
        receiver = _make_account(client, "AL_NullTxnR", 0)

        r = _transfer(client, sender["account_id"], receiver["account_id"], 99_999, "al-fail-nulltxn-001")
        assert r.status_code == 422

        with db_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT transaction_id FROM audit_logs "
                    "WHERE action = 'TRANSFER_FAILED' AND actor = :actor "
                    "ORDER BY rowid DESC LIMIT 1"
                ),
                {"actor": sender["account_id"]},
            ).fetchone()

        assert row is not None
        assert row[0] is None, f"Expected NULL transaction_id for failed transfer, got {row[0]}"


# ═══════════════════════════════════════════════════════════════════════════════
# AuditLog: no missing entries (every transfer attempt is logged)
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditLogCompleteness:
    def test_every_transfer_attempt_has_audit(self, client, db_engine):
        """모든 송금 시도(성공+실패)에 감사로그 누락 없음."""
        sender = _make_account(client, "AL_Complete_S", 50_000)
        receiver = _make_account(client, "AL_Complete_R", 0)

        # 1 success
        r1 = _transfer(client, sender["account_id"], receiver["account_id"], 1_000, "al-comp-001")
        assert r1.status_code == 200

        # 2 failures
        r2 = _transfer(client, sender["account_id"], receiver["account_id"], 999_999, "al-comp-002")
        assert r2.status_code == 422

        ghost = "00000000-0000-0000-0000-111111111111"
        r3 = _transfer(client, sender["account_id"], ghost, 500, "al-comp-003")
        assert r3.status_code == 404

        with db_engine.connect() as conn:
            success_count = conn.execute(
                text(
                    "SELECT COUNT(*) FROM audit_logs "
                    "WHERE action = 'TRANSFER' AND actor = :actor"
                ),
                {"actor": sender["account_id"]},
            ).scalar()
            failure_count = conn.execute(
                text(
                    "SELECT COUNT(*) FROM audit_logs "
                    "WHERE action = 'TRANSFER_FAILED' AND actor = :actor"
                ),
                {"actor": sender["account_id"]},
            ).scalar()

        assert success_count == 1, f"Expected 1 success audit, got {success_count}"
        assert failure_count == 2, f"Expected 2 failure audits, got {failure_count}"


# ═══════════════════════════════════════════════════════════════════════════════
# Sub-AC 5b: DB-level trigger blocks UPDATE/DELETE on audit_logs
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditLogTriggerImmutability:
    """SQLite BEFORE UPDATE/DELETE triggers raise IntegrityError at DB level."""

    def _insert_audit_row(self, db_engine, row_id: str) -> None:
        """INSERT a raw audit_log row directly (bypassing ORM) for trigger testing."""
        with db_engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO audit_logs "
                    "(audit_log_id, actor, action, reason, status, timestamp) "
                    "VALUES (:rid, 'trigger-test', 'TRIGGER_TEST', "
                    "'immutability check', 'success', '2024-01-01T00:00:00+00:00')"
                ),
                {"rid": row_id},
            )
            conn.commit()

    def test_update_audit_log_blocked_by_trigger(self, db_engine):
        """직접 UPDATE 시도 → SQLite 트리거가 IntegrityError 발생."""
        row_id = "trigger-test-update-001"
        self._insert_audit_row(db_engine, row_id)

        with pytest.raises(IntegrityError):
            with db_engine.connect() as conn:
                conn.execute(
                    text(
                        "UPDATE audit_logs SET actor = 'hacked' "
                        "WHERE audit_log_id = :id"
                    ),
                    {"id": row_id},
                )
                conn.commit()

    def test_delete_audit_log_blocked_by_trigger(self, db_engine):
        """직접 DELETE 시도 → SQLite 트리거가 IntegrityError 발생."""
        row_id = "trigger-test-delete-001"
        self._insert_audit_row(db_engine, row_id)

        with pytest.raises(IntegrityError):
            with db_engine.connect() as conn:
                conn.execute(
                    text(
                        "DELETE FROM audit_logs WHERE audit_log_id = :id"
                    ),
                    {"id": row_id},
                )
                conn.commit()

    def test_row_unchanged_after_blocked_update(self, db_engine):
        """UPDATE 거부 후 원본 row actor 값 변경 없음 (데이터 무결성 보존)."""
        row_id = "trigger-test-persist-001"
        self._insert_audit_row(db_engine, row_id)

        # Attempt update — expected to fail
        try:
            with db_engine.connect() as conn:
                conn.execute(
                    text(
                        "UPDATE audit_logs SET actor = 'hacked' "
                        "WHERE audit_log_id = :id"
                    ),
                    {"id": row_id},
                )
                conn.commit()
        except IntegrityError:
            pass  # expected

        # Row must still exist with original actor
        with db_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT actor FROM audit_logs WHERE audit_log_id = :id"
                ),
                {"id": row_id},
            ).fetchone()

        assert row is not None, "Row must still exist after blocked UPDATE"
        assert row[0] == "trigger-test", (
            f"actor must be unchanged; got '{row[0]}'"
        )
