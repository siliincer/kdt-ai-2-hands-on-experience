"""Execution Context DB 접근.

계층 규칙: session.commit() 등 DB 접근은 repository 에만 둔다(BE_Coding.md).
발급(create)·조회(get)만 제공하고 검증·만료 판정은 service 계층이 담당한다.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.execution_context import ExecutionContext, ExecutionContextStatus


async def create_execution_context(
    session: AsyncSession,
    user_id: UUID,
    chat_session_id: UUID,
    scopes: list[str],
    expires_at: datetime,
    timezone: str,
    agent_thread_id: str | None = None,
) -> ExecutionContext:
    """새 실행 Context 를 발급·저장한다(정본은 Backend)."""
    context = ExecutionContext(
        user_id=user_id,
        chat_session_id=chat_session_id,
        scopes=scopes,
        expires_at=expires_at,
        timezone=timezone,
        agent_thread_id=agent_thread_id,
        status=ExecutionContextStatus.ACTIVE,
    )
    session.add(context)
    await session.commit()
    await session.refresh(context)
    return context


async def get_execution_context_by_id(
    session: AsyncSession, execution_context_id: UUID
) -> ExecutionContext | None:
    """id 로 실행 Context 를 조회한다(없으면 None)."""
    stmt = select(ExecutionContext).where(ExecutionContext.id == execution_context_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
