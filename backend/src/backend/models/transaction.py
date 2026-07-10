from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.postgres import Base

if TYPE_CHECKING:
    from .account import Account
    from .approval import Approval


class TransactionStatus(PyEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# TODO: 계정계 서버를 mock-financial-service로 분리함에 따라 deprecate 예정
class TransactionType(PyEnum):
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    TRANSFER = "TRANSFER"
    INQUIRY = "INQUIRY"


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sender_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False
    )
    receiver_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus, name="transaction_status"),
        nullable=False,
        default=TransactionStatus.PENDING,
    )
    tx_type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, name="transaction_type"),
        nullable=False,
        default=TransactionType.INQUIRY,
    )
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    sender_account: Mapped["Account"] = relationship(
        back_populates="sent_transactions",
        lazy="selectin",
        foreign_keys=[sender_account_id],
    )
    receiver_account: Mapped["Account"] = relationship(
        back_populates="received_transactions",
        lazy="selectin",
        foreign_keys=[receiver_account_id],
    )
    approvals: Mapped[list["Approval"]] = relationship(
        back_populates="transaction",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
