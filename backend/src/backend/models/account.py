from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.postgres import Base

# 타입 검사 도구에게만 클래스 위치를 알려줌 (런타임에는 실행 안 됨)
if TYPE_CHECKING:
    from .transaction import Transaction
    from .user import User


# TODO: 계정계 서버를 mock-financial-service로 분리함에 따라 deprecate 예정
class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    account_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    balance: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="KRW")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # mock-financial-service(계정계) 원장의 account_id 매핑. 잔액/원장의 권위는
    # 계정계로 이관되므로 이 컬럼이 로컬 User <-> 외부 계좌를 잇는다.
    # nullable: 프로비저닝(Phase 2) 전 기존 행 호환.
    external_account_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True
    )

    user: Mapped["User"] = relationship(
        back_populates="accounts",
        lazy="selectin",
        # lazy="selectin": IN 방식 사용: 부모를 조회하는 쿼리를 먼저 실행한 후,
        # 부모들의 PK 값을 모아서 IN 절을 사용한 두 번째 쿼리로
        # 자식들을 따로 가져옵니다.
    )
    sent_transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="sender_account",
        lazy="selectin",
        foreign_keys="Transaction.sender_account_id",
        cascade="all, delete-orphan",
    )
    received_transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="receiver_account",
        lazy="selectin",
        foreign_keys="Transaction.receiver_account_id",
        cascade="all, delete-orphan",
    )
