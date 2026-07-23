from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.postgres import Base

if TYPE_CHECKING:
    from .confirmation import Confirmation
    from .user import User


class AuthContextStatus(PyEnum):
    """추가 인증 시도의 상태.

    계약의 `auth_status` Enum(verified/failed/cancelled/expired)에 대응한다.
    PENDING 은 생성 직후 인증 대기 상태다(계약에는 별도 노출하지 않음).
    """

    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


# 하나의 Confirmation 에 대한 추가 인증 시도(계약 15장).
# 인증 원문(PIN·생체 Assertion)은 저장하지 않는다 — Backend 는 결과 상태만 관리하고
# Agent 에는 상태만 전달한다(계약 15.4·25.3).
# 인증 실패·만료 후 재시도하면 새 Auth Context 를 만들어 Confirmation 당 N 건이 쌓인다.
class AuthContext(Base):
    __tablename__ = "auth_contexts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    confirmation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("confirmations.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[AuthContextStatus] = mapped_column(
        Enum(AuthContextStatus, name="auth_context_status"),
        nullable=False,
        default=AuthContextStatus.PENDING,
        index=True,
    )
    # 예: ["biometric", "password"] — Frontend 인증 UI 가 제시할 수단.
    available_methods: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # 서비스는 컬럼(user_id/confirmation_id)만 사용 → 자동 로딩 안 함(R4).
    user: Mapped["User"] = relationship(lazy="raise")
    confirmation: Mapped["Confirmation"] = relationship(lazy="raise")
