"""추가 인증 Context DB 접근(계약 15장).

인증 원문은 저장하지 않는다 — 상태·만료만 관리한다.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.auth_context import AuthContext, AuthContextStatus


async def create_auth_context(
    session: AsyncSession,
    confirmation_id: UUID,
    user_id: UUID,
    available_methods: list[str],
    expires_at: datetime,
) -> AuthContext:
    """새 인증 시도(PENDING)를 생성한다."""
    auth_context = AuthContext(
        confirmation_id=confirmation_id,
        user_id=user_id,
        available_methods=available_methods,
        expires_at=expires_at,
        status=AuthContextStatus.PENDING,
    )
    session.add(auth_context)
    await session.commit()
    await session.refresh(auth_context)
    return auth_context


async def get_auth_context_by_id(session: AsyncSession, auth_context_id: UUID) -> AuthContext | None:
    """id 로 Auth Context 를 조회한다(없으면 None)."""
    stmt = select(AuthContext).where(AuthContext.id == auth_context_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_active_auth_context(session: AsyncSession, confirmation_id: UUID, now: datetime) -> AuthContext | None:
    """같은 Confirmation 의 아직 살아있는 인증 시도(PENDING·미만료)를 찾는다.

    계약 15.4 의 "같은 Confirmation 의 활성 Auth Context 존재 여부" 검증에 사용한다.
    """
    stmt = select(AuthContext).where(
        AuthContext.confirmation_id == confirmation_id,
        AuthContext.status == AuthContextStatus.PENDING,
        AuthContext.expires_at > now,
    )
    result = await session.execute(stmt)
    return result.scalars().first()


async def set_auth_context_status(
    session: AsyncSession,
    auth_context: AuthContext,
    status: AuthContextStatus,
    verified_at: datetime | None = None,
) -> AuthContext:
    """인증 결과 상태를 전이시키고 저장한다."""
    auth_context.status = status
    if verified_at is not None:
        auth_context.verified_at = verified_at
    await session.commit()
    await session.refresh(auth_context)
    return auth_context
