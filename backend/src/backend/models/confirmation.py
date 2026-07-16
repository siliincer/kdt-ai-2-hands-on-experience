from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Enum, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.postgres import Base

if TYPE_CHECKING:
    from .execution_context import ExecutionContext
    from .user import User


class ConfirmationStatus(PyEnum):
    PENDING = "PENDING"  # Prepare 로 생성, 사용자 승인 대기
    APPROVED = "APPROVED"  # 사용자 승인 완료, Execute 가능
    INVALIDATED = "INVALIDATED"  # 사용자가 조건을 수정해 재사용 불가
    CANCELLED = "CANCELLED"  # 사용자가 취소
    EXECUTED = "EXECUTED"  # 실행 완료(1회만 가능)
    EXPIRED = "EXPIRED"  # 만료


class ConfirmationOperation(PyEnum):
    DEFAULT_ACCOUNT_CHANGE = "DEFAULT_ACCOUNT_CHANGE"
    ACCOUNT_ALIAS_CHANGE = "ACCOUNT_ALIAS_CHANGE"
    INTERNAL_TRANSFER = "INTERNAL_TRANSFER"
    EXTERNAL_TRANSFER = "EXTERNAL_TRANSFER"


# Prepare 가 승인 대상(계좌·별칭·금액 등)을 고정해 두는 리소스(계약 5·14·19·21장).
# 기존 approvals 테이블을 대체한다(D3): approvals 는 transaction_id FK 가 필수라
# 원장 거래가 아직 없는 Prepare 시점을 표현할 수 없었다.
# Execute 는 이 행의 status/만료/미실행 여부를 다시 검증한 뒤에만 진행한다.
class Confirmation(Base):
    __tablename__ = "confirmations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    execution_context_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("execution_contexts.id"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    operation: Mapped[ConfirmationOperation] = mapped_column(
        Enum(ConfirmationOperation, name="confirmation_operation"), nullable=False
    )
    status: Mapped[ConfirmationStatus] = mapped_column(
        Enum(ConfirmationStatus, name="confirmation_status"),
        nullable=False,
        default=ConfirmationStatus.PENDING,
        index=True,
    )
    # Prepare 시점에 고정한 승인 대상 데이터. Execute 는 요청 본문이 아니라
    # 이 값을 신뢰해 실행한다(Agent 가 Execute 에 업무 값을 다시 보내지 않음).
    fixed_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship(lazy="selectin")
    execution_context: Mapped["ExecutionContext"] = relationship(lazy="selectin")
