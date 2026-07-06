"""CRUD operations via SQLAlchemy ORM only — no raw SQL."""

import hashlib
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Account, AuditLog, LedgerEntry, Transaction
from .schemas import AccountCreate, TransferRequest

# ── helpers ───────────────────────────────────────────────────────────────────


def _payload_hash(data: dict) -> str:
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _get_balance(db: Session, account_id: str) -> int:
    """Compute balance from ledger entries (double-entry sum)."""
    credits = (
        db.execute(
            select(func.coalesce(func.sum(LedgerEntry.amount), 0))
            .where(LedgerEntry.account_id == account_id)
            .where(LedgerEntry.entry_type == "CREDIT")
        ).scalar()
        or 0
    )
    debits = (
        db.execute(
            select(func.coalesce(func.sum(LedgerEntry.amount), 0))
            .where(LedgerEntry.account_id == account_id)
            .where(LedgerEntry.entry_type == "DEBIT")
        ).scalar()
        or 0
    )
    return int(credits) - int(debits)


def _append_audit(
    db: Session,
    *,
    actor: str,
    action: str,
    reason: str,
    status: str,
    transaction_id: str | None = None,
    payload_snapshot: str | None = None,
) -> AuditLog:
    log = AuditLog(
        actor=actor,
        action=action,
        reason=reason,
        status=status,
        transaction_id=transaction_id,
        payload_snapshot=payload_snapshot,
    )
    db.add(log)
    return log


# ── Account ───────────────────────────────────────────────────────────────────


def create_account(db: Session, payload: AccountCreate) -> tuple[Account, int]:
    acct = Account(owner=payload.owner)
    db.add(acct)
    db.flush()  # get account_id before ledger entry

    balance = 0
    if payload.initial_balance > 0:
        # Seed credit (initial deposit has no counterpart — system account)
        entry = LedgerEntry(
            transaction_id=_create_seed_transaction(
                db, acct.account_id, payload.initial_balance
            ),
            account_id=acct.account_id,
            entry_type="CREDIT",
            amount=payload.initial_balance,
            running_balance=payload.initial_balance,
        )
        db.add(entry)
        balance = payload.initial_balance

    _append_audit(
        db,
        actor=payload.owner,
        action="ACCOUNT_CREATE",
        reason=f"New account created for {payload.owner}",
        status="success",
        payload_snapshot=json.dumps(
            {"owner": payload.owner, "initial_balance": payload.initial_balance}
        ),
    )
    db.commit()
    db.refresh(acct)
    return acct, balance


def _create_seed_transaction(db: Session, account_id: str, amount: int) -> str:
    """Synthetic transaction for initial deposit (system→account)."""

    txn = Transaction(
        idempotency_key=f"__seed__{account_id}",
        payload_hash=_payload_hash({"seed": account_id, "amount": amount}),
        sender_account_id=account_id,
        receiver_account_id=account_id,
        amount=amount,
        status="success",
    )
    db.add(txn)
    db.flush()
    return txn.transaction_id


def get_account(db: Session, account_id: str) -> Account | None:
    return db.execute(
        select(Account).where(Account.account_id == account_id)
    ).scalar_one_or_none()


def get_balance(db: Session, account_id: str) -> int:
    return _get_balance(db, account_id)


def get_ledger_entries(
    db: Session, account_id: str, limit: int = 50, offset: int = 0
) -> list[LedgerEntry]:
    result = (
        db.execute(
            select(LedgerEntry)
            .where(LedgerEntry.account_id == account_id)
            .order_by(LedgerEntry.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return list(result)


# ── Transfer ──────────────────────────────────────────────────────────────────


def _write_failure_audit(
    db: Session,
    *,
    actor: str,
    reason: str,
    error_code: str,
    payload: "TransferRequest",
    idempotency_key: str,
) -> None:
    """Write failure audit log in a fresh DB state (after rollback if needed)."""
    _append_audit(
        db,
        actor=actor,
        action="TRANSFER_FAILED",
        reason=f"[{error_code}] {reason}",
        status="failure",
        transaction_id=None,
        payload_snapshot=json.dumps(
            {
                "sender": payload.sender_account_id,
                "receiver": payload.receiver_account_id,
                "amount": payload.amount,
                "idempotency_key": idempotency_key,
                "error_code": error_code,
            }
        ),
    )
    db.commit()


def transfer(
    db: Session,
    payload: TransferRequest,
    idempotency_key: str,
) -> Transaction:
    phash = _payload_hash(
        {
            "sender_account_id": payload.sender_account_id,
            "receiver_account_id": payload.receiver_account_id,
            "amount": payload.amount,
        }
    )

    # Idempotency check
    existing = db.execute(
        select(Transaction).where(Transaction.idempotency_key == idempotency_key)
    ).scalar_one_or_none()

    if existing is not None:
        if existing.payload_hash != phash:
            _write_failure_audit(
                db,
                actor=payload.sender_account_id,
                reason="Idempotency key reused with different payload",
                error_code="IDEMPOTENCY_CONFLICT",
                payload=payload,
                idempotency_key=idempotency_key,
            )
            raise ConflictError(
                "IDEMPOTENCY_CONFLICT", "Idempotency key reused with different payload"
            )
        return existing  # safe replay

    try:
        # Validate accounts
        if payload.sender_account_id == payload.receiver_account_id:
            raise ValidationError("SELF_TRANSFER", "Sender and receiver must differ")

        sender = get_account(db, payload.sender_account_id)
        if sender is None:
            raise NotFoundError(
                "ACCOUNT_NOT_FOUND", f"Sender {payload.sender_account_id} not found"
            )

        receiver = get_account(db, payload.receiver_account_id)
        if receiver is None:
            raise NotFoundError(
                "ACCOUNT_NOT_FOUND", f"Receiver {payload.receiver_account_id} not found"
            )

        if payload.amount <= 0:
            raise ValidationError("INVALID_AMOUNT", "Amount must be positive integer")

        sender_balance = _get_balance(db, payload.sender_account_id)
        if sender_balance < payload.amount:
            raise ValidationError(
                "INSUFFICIENT_BALANCE", f"Balance {sender_balance} < {payload.amount}"
            )

        receiver_balance = _get_balance(db, payload.receiver_account_id)

        # Capture pre-transfer total for post-commit integrity assertion
        pre_transfer_total = sender_balance + receiver_balance

        # Create transaction record
        txn = Transaction(
            idempotency_key=idempotency_key,
            payload_hash=phash,
            sender_account_id=payload.sender_account_id,
            receiver_account_id=payload.receiver_account_id,
            amount=payload.amount,
            status="success",
        )
        db.add(txn)
        db.flush()

        # Double-entry: DEBIT sender, CREDIT receiver (atomic pair)
        debit = LedgerEntry(
            transaction_id=txn.transaction_id,
            account_id=payload.sender_account_id,
            entry_type="DEBIT",
            amount=payload.amount,
            running_balance=sender_balance - payload.amount,
        )
        credit = LedgerEntry(
            transaction_id=txn.transaction_id,
            account_id=payload.receiver_account_id,
            entry_type="CREDIT",
            amount=payload.amount,
            running_balance=receiver_balance + payload.amount,
        )
        db.add(debit)
        db.add(credit)

        _append_audit(
            db,
            actor=payload.sender_account_id,
            action="TRANSFER",
            reason=f"Transfer {payload.amount} KRW to {payload.receiver_account_id}",
            status="success",
            transaction_id=txn.transaction_id,
            payload_snapshot=json.dumps(
                {
                    "sender": payload.sender_account_id,
                    "receiver": payload.receiver_account_id,
                    "amount": payload.amount,
                    "idempotency_key": idempotency_key,
                }
            ),
        )
        db.commit()
        db.refresh(txn)

    except ServiceError as exc:
        db.rollback()
        _write_failure_audit(
            db,
            actor=payload.sender_account_id,
            reason=exc.message,
            error_code=exc.error_code,
            payload=payload,
            idempotency_key=idempotency_key,
        )
        raise

    # Runtime integrity assertion: total balance must be preserved after commit
    post_sender_balance = _get_balance(db, payload.sender_account_id)
    post_receiver_balance = _get_balance(db, payload.receiver_account_id)
    post_transfer_total = post_sender_balance + post_receiver_balance
    assert post_transfer_total == pre_transfer_total, (
        f"Balance integrity violation: pre={pre_transfer_total}, "
        f"post={post_transfer_total} "
        f"(sender={post_sender_balance}, receiver={post_receiver_balance})"
    )

    return txn


# ── Custom exceptions ─────────────────────────────────────────────────────────


class ServiceError(Exception):
    def __init__(self, error_code: str, message: str):
        self.error_code = error_code
        self.message = message
        super().__init__(message)


class ValidationError(ServiceError):
    pass


class NotFoundError(ServiceError):
    pass


class ConflictError(ServiceError):
    pass
