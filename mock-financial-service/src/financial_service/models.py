"""SQLAlchemy ORM models for double-entry ledger."""

import random
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import BigInteger, Date, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

# 이 mock 서비스가 표현하는 단일 은행명 — 모든 계좌에 고정 부여
BANK_NAME = "KDT은행"


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _generate_account_number() -> str:
    """국내 은행 계좌번호 관용 포맷(3-3-6자리)으로 랜덤 생성."""
    return (
        f"{random.randint(0, 999):03d}-"
        f"{random.randint(0, 999):03d}-"
        f"{random.randint(0, 999999):06d}"
    )


class Account(Base):
    __tablename__ = "accounts"

    account_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    bank_name: Mapped[str] = mapped_column(
        String(50), nullable=False, default=BANK_NAME
    )
    account_number: Mapped[str] = mapped_column(
        String(20), nullable=False, unique=True, default=_generate_account_number
    )
    # canonical live balance — updated atomically with every ledger_entries write
    # (same DB transaction). _get_balance() (full SUM over ledger_entries) exists
    # only to verify this value is legit — see crud.reconcile_balance().
    balance: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
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


class DailyClosingSnapshot(Base):
    """일일 마감(EOD) 배치 결과 — 계좌×영업일 조합당 1행, append-only 이력.

    balance_snapshots(단일행 덮어쓰기)와 달리 영업일별로 행이 누적된다.
    business_date 당 1행만 존재하도록 복합 PK로 강제 — 같은 날 배치를 여러 번
    돌려도 중복 insert 없음 (run_daily_closing()의 exists-check가 1차 방어,
    PK가 최종 방어선).
    """

    __tablename__ = "daily_closing_snapshots"

    account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("accounts.account_id"), primary_key=True
    )
    business_date: Mapped[date] = mapped_column(Date, primary_key=True)
    closing_balance: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sum_credit: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sum_debit: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_entry_rowid: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
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
