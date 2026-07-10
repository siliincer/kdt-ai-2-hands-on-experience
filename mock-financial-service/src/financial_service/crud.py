"""CRUD operations via SQLAlchemy ORM only — no raw SQL."""

import hashlib
import json
from datetime import date, datetime, timezone

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .models import (
    BANK_NAME,
    Account,
    AuditLog,
    BalanceSnapshot,
    Card,
    CardLedgerEntry,
    DailyClosingSnapshot,
    LedgerEntry,
    Transaction,
)
from .schemas import AccountCreate, CardChargeRequest, CardCreate, TransferRequest

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
    seed_transaction_id: str | None = None
    if payload.initial_balance > 0:
        # Seed credit (initial deposit has no counterpart — system account)
        seed_transaction_id = _create_seed_transaction(
            db, acct.account_id, payload.initial_balance
        )
        entry = LedgerEntry(
            transaction_id=seed_transaction_id,
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
        transaction_id=seed_transaction_id,
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


def get_account_by_number(db: Session, account_number: str) -> Account | None:
    return db.execute(
        select(Account).where(Account.account_number == account_number)
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


def get_audit_logs(
    db: Session, account_id: str, limit: int = 50, offset: int = 0
) -> list[AuditLog]:
    """Audit logs linked to an account via the transaction it participated in.

    Covers ACCOUNT_CREATE (seed transaction self-links to the new account) and
    TRANSFER/TRANSFER_FAILED (transaction sender/receiver = account_id) — not
    just AuditLog.actor, since actor stores owner name on create, not account_id.
    """
    result = (
        db.execute(
            select(AuditLog)
            .join(Transaction, AuditLog.transaction_id == Transaction.transaction_id)
            .where(
                (Transaction.sender_account_id == account_id)
                | (Transaction.receiver_account_id == account_id)
            )
            .order_by(AuditLog.timestamp.desc())
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
                "sender": payload.sender_account_number,
                "receiver_bank": payload.receiver_bank_name,
                "receiver": payload.receiver_account_number,
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
            "sender_account_number": payload.sender_account_number,
            "receiver_bank_name": payload.receiver_bank_name,
            "receiver_account_number": payload.receiver_account_number,
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
                actor=payload.sender_account_number,
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
        if payload.sender_account_number == payload.receiver_account_number:
            raise ValidationError("SELF_TRANSFER", "Sender and receiver must differ")

        # 이 mock 서비스는 단일 은행만 표현 — receiver_bank_name이 그 은행이 아니면 거절
        if payload.receiver_bank_name != BANK_NAME:
            raise ValidationError(
                "BANK_NOT_SUPPORTED",
                f"Unsupported bank: {payload.receiver_bank_name} (only {BANK_NAME})",
            )

        sender = get_account_by_number(db, payload.sender_account_number)
        if sender is None:
            raise NotFoundError(
                "ACCOUNT_NOT_FOUND", f"Sender {payload.sender_account_number} not found"
            )

        receiver = get_account_by_number(db, payload.receiver_account_number)
        if receiver is None:
            raise NotFoundError(
                "ACCOUNT_NOT_FOUND",
                f"Receiver {payload.receiver_account_number} not found",
            )

        sender_id = sender.account_id
        receiver_id = receiver.account_id

        if payload.amount <= 0:
            raise ValidationError("INVALID_AMOUNT", "Amount must be positive integer")

        sender_balance = _get_balance(db, sender_id)
        if sender_balance < payload.amount:
            raise ValidationError(
                "INSUFFICIENT_BALANCE", f"Balance {sender_balance} < {payload.amount}"
            )

        receiver_balance = _get_balance(db, receiver_id)

        # Capture pre-transfer total for post-commit integrity assertion
        pre_transfer_total = sender_balance + receiver_balance

        # Create transaction record
        txn = Transaction(
            idempotency_key=idempotency_key,
            payload_hash=phash,
            sender_account_id=sender_id,
            receiver_account_id=receiver_id,
            amount=payload.amount,
            status="success",
        )
        db.add(txn)
        db.flush()

        # Double-entry: DEBIT sender, CREDIT receiver (atomic pair)
        debit = LedgerEntry(
            transaction_id=txn.transaction_id,
            account_id=sender_id,
            entry_type="DEBIT",
            amount=payload.amount,
            running_balance=sender_balance - payload.amount,
        )
        credit = LedgerEntry(
            transaction_id=txn.transaction_id,
            account_id=receiver_id,
            entry_type="CREDIT",
            amount=payload.amount,
            running_balance=receiver_balance + payload.amount,
        )
        db.add(debit)
        db.add(credit)

        _append_audit(
            db,
            actor=payload.sender_account_number,
            action="TRANSFER",
            reason=(
                f"Transfer {payload.amount} KRW to {payload.receiver_account_number}"
            ),
            status="success",
            transaction_id=txn.transaction_id,
            payload_snapshot=json.dumps(
                {
                    "sender": payload.sender_account_number,
                    "receiver_bank": payload.receiver_bank_name,
                    "receiver": payload.receiver_account_number,
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
            actor=payload.sender_account_number,
            reason=exc.message,
            error_code=exc.error_code,
            payload=payload,
            idempotency_key=idempotency_key,
        )
        raise

    # Runtime integrity assertion: total balance must be preserved after commit
    post_sender_balance = _get_balance(db, txn.sender_account_id)
    post_receiver_balance = _get_balance(db, txn.receiver_account_id)
    post_transfer_total = post_sender_balance + post_receiver_balance
    assert post_transfer_total == pre_transfer_total, (
        f"Balance integrity violation: pre={pre_transfer_total}, "
        f"post={post_transfer_total} "
        f"(sender={post_sender_balance}, receiver={post_receiver_balance})"
    )

    return txn


# ── Snapshot / 정보계 balance cache ───────────────────────────────────────────


def refresh_snapshot(db: Session, account_id: str) -> BalanceSnapshot:
    """Compute and overwrite single-row snapshot for account.

    Semantics: one row per account, mutable, overwritten in-place.
    Never append-only — calling twice leaves exactly 1 row.
    """
    sum_credit = int(
        db.execute(
            select(func.coalesce(func.sum(LedgerEntry.amount), 0))
            .where(LedgerEntry.account_id == account_id)
            .where(LedgerEntry.entry_type == "CREDIT")
        ).scalar()
        or 0
    )
    sum_debit = int(
        db.execute(
            select(func.coalesce(func.sum(LedgerEntry.amount), 0))
            .where(LedgerEntry.account_id == account_id)
            .where(LedgerEntry.entry_type == "DEBIT")
        ).scalar()
        or 0
    )
    # SQLite rowid as integer high-water-mark
    last_rowid = db.execute(
        text("SELECT MAX(rowid) FROM ledger_entries WHERE account_id = :aid"),
        {"aid": account_id},
    ).scalar()

    cached_balance = sum_credit - sum_debit
    now = datetime.now(timezone.utc)

    existing = db.execute(
        select(BalanceSnapshot).where(BalanceSnapshot.account_id == account_id)
    ).scalar_one_or_none()

    if existing is not None:
        # Overwrite in-place — never append
        existing.cached_balance = cached_balance
        existing.last_entry_rowid = last_rowid
        existing.sum_credit = sum_credit
        existing.sum_debit = sum_debit
        existing.refreshed_at = now
        snap = existing
    else:
        snap = BalanceSnapshot(
            account_id=account_id,
            cached_balance=cached_balance,
            last_entry_rowid=last_rowid,
            sum_credit=sum_credit,
            sum_debit=sum_debit,
            refreshed_at=now,
        )
        db.add(snap)

    db.commit()
    db.refresh(snap)
    return snap


def get_snapshot(db: Session, account_id: str) -> BalanceSnapshot | None:
    """Fetch existing snapshot row (None if not yet refreshed)."""
    return db.execute(
        select(BalanceSnapshot).where(BalanceSnapshot.account_id == account_id)
    ).scalar_one_or_none()


def reconcile_snapshot(db: Session, account_id: str) -> dict:
    """Compare watermark-scoped stored sums vs live recompute.

    Pure function — no locking, no writes, does not block ledger writes.
    Scope: only ledger entries with rowid <= last_entry_rowid are compared.
    """
    snap = get_snapshot(db, account_id)
    if snap is None:
        live_balance = _get_balance(db, account_id)
        return {
            "account_id": account_id,
            "cached_balance": 0,
            "expected_balance": live_balance,
            "sum_credit": 0,
            "sum_debit": 0,
            "last_entry_rowid": None,
            "drift_detected": live_balance != 0,
            "delta": -live_balance,
            "reconciled_at": datetime.now(timezone.utc).isoformat(),
        }

    if snap.last_entry_rowid is not None:
        recomputed_credit = int(
            db.execute(
                text(
                    "SELECT COALESCE(SUM(amount), 0) FROM ledger_entries "
                    "WHERE account_id = :aid AND entry_type = 'CREDIT' AND rowid <= :wm"
                ),
                {"aid": account_id, "wm": snap.last_entry_rowid},
            ).scalar()
            or 0
        )
        recomputed_debit = int(
            db.execute(
                text(
                    "SELECT COALESCE(SUM(amount), 0) FROM ledger_entries "
                    "WHERE account_id = :aid AND entry_type = 'DEBIT' AND rowid <= :wm"
                ),
                {"aid": account_id, "wm": snap.last_entry_rowid},
            ).scalar()
            or 0
        )
    else:
        recomputed_credit = 0
        recomputed_debit = 0

    expected_balance = recomputed_credit - recomputed_debit
    delta = snap.cached_balance - expected_balance
    drift_detected = delta != 0

    return {
        "account_id": account_id,
        "cached_balance": snap.cached_balance,
        "expected_balance": expected_balance,
        "sum_credit": snap.sum_credit,
        "sum_debit": snap.sum_debit,
        "last_entry_rowid": snap.last_entry_rowid,
        "drift_detected": drift_detected,
        "delta": delta,
        "reconciled_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Daily Closing (EOD batch) ──────────────────────────────────────────────────


def run_daily_closing(
    db: Session, business_date: date | None = None
) -> tuple[date, list[DailyClosingSnapshot]]:
    """EOD 마감 배치 — 모든 계좌를 대상으로 영업일당 1행 insert.

    실제 cron/스케줄러 없음 — scripts/run_daily_close.py 를 OS cron(자정)에
    등록해 호출하거나, 이 함수를 감싼 POST /api/v1/batch/daily-close 로 수동
    트리거. 같은 business_date에 이미 마감된 계좌는 스킵(idempotent) — 재실행
    해도 중복 행 없음(모델의 (account_id, business_date) 복합 PK가 최종 방어).
    """
    if business_date is None:
        business_date = datetime.now(timezone.utc).date()

    accounts = db.execute(select(Account)).scalars().all()
    created: list[DailyClosingSnapshot] = []

    for acct in accounts:
        existing = db.execute(
            select(DailyClosingSnapshot).where(
                DailyClosingSnapshot.account_id == acct.account_id,
                DailyClosingSnapshot.business_date == business_date,
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue  # already closed for this business_date — idempotent skip

        sum_credit = int(
            db.execute(
                select(func.coalesce(func.sum(LedgerEntry.amount), 0))
                .where(LedgerEntry.account_id == acct.account_id)
                .where(LedgerEntry.entry_type == "CREDIT")
            ).scalar()
            or 0
        )
        sum_debit = int(
            db.execute(
                select(func.coalesce(func.sum(LedgerEntry.amount), 0))
                .where(LedgerEntry.account_id == acct.account_id)
                .where(LedgerEntry.entry_type == "DEBIT")
            ).scalar()
            or 0
        )
        last_rowid = db.execute(
            text("SELECT MAX(rowid) FROM ledger_entries WHERE account_id = :aid"),
            {"aid": acct.account_id},
        ).scalar()

        row = DailyClosingSnapshot(
            account_id=acct.account_id,
            business_date=business_date,
            closing_balance=sum_credit - sum_debit,
            sum_credit=sum_credit,
            sum_debit=sum_debit,
            last_entry_rowid=last_rowid,
        )
        db.add(row)
        created.append(row)

    _append_audit(
        db,
        actor="SYSTEM_BATCH",
        action="DAILY_CLOSE",
        reason=(
            f"Daily closing batch for {business_date}: {len(created)} accounts closed"
        ),
        status="success",
        payload_snapshot=json.dumps(
            {
                "business_date": business_date.isoformat(),
                "accounts_closed": len(created),
            }
        ),
    )
    db.commit()
    for row in created:
        db.refresh(row)
    return business_date, created


def list_daily_closings(
    db: Session, account_id: str, limit: int = 50, offset: int = 0
) -> list[DailyClosingSnapshot]:
    result = (
        db.execute(
            select(DailyClosingSnapshot)
            .where(DailyClosingSnapshot.account_id == account_id)
            .order_by(DailyClosingSnapshot.business_date.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return list(result)


# ── Card ──────────────────────────────────────────────────────────────────────

CARD_SETTLEMENT = "CARD_SETTLEMENT"


def create_card(db: Session, payload: CardCreate) -> Card:
    """Create a card under an existing account."""
    acct = get_account(db, payload.account_id)
    if acct is None:
        raise NotFoundError(
            "ACCOUNT_NOT_FOUND", f"Account {payload.account_id} not found"
        )

    card = Card(
        account_id=payload.account_id,
        limit=payload.limit,
        currency=payload.currency,
    )
    db.add(card)
    db.flush()

    _append_audit(
        db,
        actor=payload.account_id,
        action="CARD_CREATE",
        reason=(
            f"Card created for account {payload.account_id} with limit {payload.limit}"
        ),
        status="success",
        payload_snapshot=json.dumps(
            {
                "account_id": payload.account_id,
                "limit": payload.limit,
                "currency": payload.currency,
            }
        ),
    )
    db.commit()
    db.refresh(card)
    return card


def get_card(db: Session, card_id: str) -> Card | None:
    return db.execute(select(Card).where(Card.card_id == card_id)).scalar_one_or_none()


def _get_card_watermark(db: Session, card_id: str) -> int:
    """Highest card-ledger rowid covered by the latest settlement (0 if none)."""
    result = db.execute(
        select(func.max(Transaction.settlement_watermark_rowid)).where(
            Transaction.settlement_type == CARD_SETTLEMENT,
            Transaction.settlement_card_id == card_id,
        )
    ).scalar()
    return int(result) if result is not None else 0


def _get_unsettled_usage(db: Session, card_id: str, watermark: int) -> int:
    """SUM of card-ledger entries with rowid strictly > watermark."""
    result = db.execute(
        text(
            "SELECT COALESCE(SUM(amount), 0) FROM card_ledger_entries "
            "WHERE card_id = :cid AND rowid > :wm"
        ),
        {"cid": card_id, "wm": watermark},
    ).scalar()
    return int(result) if result is not None else 0


def charge_card(
    db: Session,
    card_id: str,
    payload: CardChargeRequest,
    idempotency_key: str,
) -> CardLedgerEntry:
    """Record a card purchase in the card ledger. Account untouched until settlement."""
    card = get_card(db, card_id)
    if card is None:
        raise NotFoundError("CARD_NOT_FOUND", f"Card {card_id} not found")

    # Idempotency: if same key exists, replay
    existing = db.execute(
        select(CardLedgerEntry).where(
            CardLedgerEntry.idempotency_key == idempotency_key
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    # Limit check: unsettled_usage + new_charge <= limit
    watermark = _get_card_watermark(db, card_id)
    unsettled = _get_unsettled_usage(db, card_id, watermark)
    if unsettled + payload.amount > card.limit:
        raise ValidationError(
            "CARD_LIMIT_EXCEEDED",
            f"Unsettled usage {unsettled} + charge {payload.amount} "
            f"exceeds limit {card.limit}",
        )

    entry = CardLedgerEntry(
        card_id=card_id,
        amount=payload.amount,
        idempotency_key=idempotency_key,
    )
    db.add(entry)
    db.flush()

    _append_audit(
        db,
        actor=card_id,
        action="CARD_CHARGE",
        reason=f"Card {card_id} charged {payload.amount} {card.currency}",
        status="success",
        payload_snapshot=json.dumps(
            {
                "card_id": card_id,
                "amount": payload.amount,
                "idempotency_key": idempotency_key,
            }
        ),
    )
    db.commit()
    db.refresh(entry)
    return entry


def settle_card(db: Session, card_id: str) -> Transaction:
    """Settle all unsettled card-ledger entries for a card.

    Creates a single Transaction (settlement_type=CARD_SETTLEMENT) that:
    - Debits the card owner's account for the total unsettled amount
    - Advances the settlement watermark to the highest card-ledger rowid
    No new Settlement table — reuses Transaction entity with discriminator fields.
    """
    card = get_card(db, card_id)
    if card is None:
        raise NotFoundError("CARD_NOT_FOUND", f"Card {card_id} not found")

    watermark = _get_card_watermark(db, card_id)

    # Find new watermark = MAX rowid of card_ledger_entries for this card
    new_watermark_result = db.execute(
        text("SELECT MAX(rowid) FROM card_ledger_entries WHERE card_id = :cid"),
        {"cid": card_id},
    ).scalar()
    if new_watermark_result is None or new_watermark_result <= watermark:
        raise ValidationError(
            "NOTHING_TO_SETTLE", "No unsettled card charges to settle"
        )

    new_watermark = int(new_watermark_result)
    settled_amount = _get_unsettled_usage(db, card_id, watermark)

    if settled_amount == 0:
        raise ValidationError(
            "NOTHING_TO_SETTLE", "No unsettled card charges to settle"
        )

    # Check account has sufficient balance
    account_balance = _get_balance(db, card.account_id)
    if account_balance < settled_amount:
        raise ValidationError(
            "INSUFFICIENT_BALANCE",
            f"Account balance {account_balance} < settlement amount {settled_amount}",
        )

    idempotency_key = f"__settle__{card_id}__{new_watermark}"
    phash = _payload_hash(
        {"card_id": card_id, "watermark": new_watermark, "amount": settled_amount}
    )

    txn = Transaction(
        idempotency_key=idempotency_key,
        payload_hash=phash,
        sender_account_id=card.account_id,
        receiver_account_id=card.account_id,  # self-link: debit only
        amount=settled_amount,
        status="success",
        settlement_type=CARD_SETTLEMENT,
        settlement_card_id=card_id,
        settlement_watermark_rowid=new_watermark,
    )
    db.add(txn)
    db.flush()

    # Single DEBIT entry on the card owner's account
    # (settlement reduces account balance)
    current_balance = _get_balance(db, card.account_id)
    debit = LedgerEntry(
        transaction_id=txn.transaction_id,
        account_id=card.account_id,
        entry_type="DEBIT",
        amount=settled_amount,
        running_balance=current_balance - settled_amount,
    )
    db.add(debit)

    _append_audit(
        db,
        actor=card.account_id,
        action="CARD_SETTLEMENT",
        reason=(
            f"Card {card_id} settled {settled_amount} {card.currency}; "
            f"watermark advanced to rowid {new_watermark}"
        ),
        status="success",
        transaction_id=txn.transaction_id,
        payload_snapshot=json.dumps(
            {
                "card_id": card_id,
                "settled_amount": settled_amount,
                "settlement_watermark_rowid": new_watermark,
                "account_id": card.account_id,
            }
        ),
    )
    db.commit()
    db.refresh(txn)
    return txn


def get_card_ledger_entries(
    db: Session, card_id: str, limit: int = 50, offset: int = 0
) -> list[CardLedgerEntry]:
    result = (
        db.execute(
            select(CardLedgerEntry)
            .where(CardLedgerEntry.card_id == card_id)
            .order_by(CardLedgerEntry.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return list(result)


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
