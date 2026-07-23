from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import Any

from sqlalchemy import (
    DateTime,
    Enum,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.postgres import Base


class IdempotencyStatus(PyEnum):
    IN_PROGRESS = "IN_PROGRESS"  # 선점됨, 처리 중
    COMPLETED = "COMPLETED"  # 결과 저장 완료(재호출 시 그대로 반환)


# 상태 변경 API(Prepare/Auth/Execute)의 멱등성 저장소(계약 24장).
# 같은 (context, operation, key) + 같은 Body → 최초 응답을 그대로 복원한다.
# 같은 키 + 다른 Body → IDEMPOTENCY_KEY_CONFLICT. 처리 중이면 IN_PROGRESS 로 409.
class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        # 고유성 기준은 execution_context_id + operation + idempotency_key(계약 24.3).
        UniqueConstraint(
            "execution_context_id",
            "operation",
            "idempotency_key",
            name="ux_idempotency_scope_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Audit 독립성을 위해 FK 를 걸지 않는다(Context 정리와 무관하게 보존).
    execution_context_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    # 정규화한 요청 Body 의 sha256. 같은 키에 다른 Body 인지 판별한다.
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[IdempotencyStatus] = mapped_column(
        Enum(IdempotencyStatus, name="idempotency_status"),
        nullable=False,
        default=IdempotencyStatus.IN_PROGRESS,
    )
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
