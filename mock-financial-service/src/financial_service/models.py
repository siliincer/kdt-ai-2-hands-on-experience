"""SQLAlchemy ORM models for double-entry ledger."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Account(Base):
    __tablename__ = "accounts"

    account_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="KRW")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    ledger_entries: Mapped[list["LedgerEntry"]] = relationship(
        "LedgerEntry", back_populates="account"
    )
    cards: Mapped[list["Card"]] = relationship("Card", back_populates="account")


class Card(Base):
    """카드 — 계정당 N개, 자체 한도(limit)와 카드 원장 보유."""

    __tablename__ = "cards"

    card_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("accounts.account_id"), nullable=False, index=True
    )
    limit: Mapped[int] = mapped_column(BigInteger, nullable=False)  # spending cap
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="KRW")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    account: Mapped["Account"] = relationship("Account", back_populates="cards")
    ledger_entries: Mapped[list["CardLedgerEntry"]] = relationship(
        "CardLedgerEntry", back_populates="card"
    )


class CardLedgerEntry(Base):
    """카드 원장 — 구매 시점에만 기록, 계정 잔액 미변경 (결제 전까지)."""

    __tablename__ = "card_ledger_entries"

    card_ledger_entry_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid
    )
    card_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cards.card_id"), nullable=False, index=True
    )
    amount: Mapped[int] = mapped_column(
        BigInteger, nullable=False
    )  # charge amount, non-negative
    idempotency_key: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    card: Mapped["Card"] = relationship("Card", back_populates="ledger_entries")


class Transaction(Base):
    """송금 거래 헤더 — 멱등성 키 추적.

    settlement_type discriminator:
      NULL             → normal transfer
      CARD_SETTLEMENT  → card deferred-settlement (tagged with settlement_card_id,
                         settlement_watermark_rowid)
    """

    __tablename__ = "transactions"

    transaction_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    sender_account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("accounts.account_id"), nullable=False
    )
    receiver_account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("accounts.account_id"), nullable=False
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("success", "failure", name="transaction_status"), nullable=False
    )
    # Settlement discriminator fields (null for normal transfers)
    settlement_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    settlement_card_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    settlement_watermark_rowid: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    ledger_entries: Mapped[list["LedgerEntry"]] = relationship(
        "LedgerEntry", back_populates="transaction"
    )


class LedgerEntry(Base):
    """이중기입 원장 항목 — 차변/대변 쌍."""

    __tablename__ = "ledger_entries"

    entry_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    transaction_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("transactions.transaction_id"), nullable=False
    )
    account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("accounts.account_id"), nullable=False
    )
    # DEBIT = 차변(출금, 음수), CREDIT = 대변(입금, 양수)
    entry_type: Mapped[str] = mapped_column(
        Enum("DEBIT", "CREDIT", name="entry_type"), nullable=False
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)  # always positive
    running_balance: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    account: Mapped["Account"] = relationship(
        "Account", back_populates="ledger_entries"
    )
    transaction: Mapped["Transaction"] = relationship(
        "Transaction", back_populates="ledger_entries"
    )


class BalanceSnapshot(Base):
    """정보계 잔액 캐시 — 계정당 1행, 갱신 시 덮어쓰기.

    cached_balance = SUM(CREDIT) - SUM(DEBIT) up to last_entry_rowid.
    캐시일 뿐 — canonical balance는 항상 ledger_entries에서 재계산.
    """

    __tablename__ = "balance_snapshots"

    account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("accounts.account_id"), primary_key=True
    )
    cached_balance: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # SQLite rowid high-water-mark: entries with rowid <= this value are covered
    last_entry_rowid: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sum_credit: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sum_debit: Mapped[int] = mapped_column(BigInteger, nullable=False)
    refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    account: Mapped["Account"] = relationship("Account")


class AuditLog(Base):
    """감사로그 — append-only, DB 트리거로 UPDATE/DELETE 거부."""

    __tablename__ = "audit_logs"

    audit_log_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid
    )
    transaction_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("success", "failure", name="audit_status"), nullable=False
    )
    payload_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
