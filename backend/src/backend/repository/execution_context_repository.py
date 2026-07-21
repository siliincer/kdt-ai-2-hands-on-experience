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


async def get_execution_context_by_id(session: AsyncSession, execution_context_id: UUID) -> ExecutionContext | None:
    """id 로 실행 Context 를 조회한다(없으면 None)."""
    stmt = select(ExecutionContext).where(ExecutionContext.id == execution_context_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def set_agent_thread_id(
    session: AsyncSession, context: ExecutionContext, agent_thread_id: str
) -> ExecutionContext:
    """Agent 실행 시작 응답으로 받은 agent_thread_id 를 Context 에 연결한다.

    thread 발급 주체가 Agent 이므로 발급 시점(issue_context)엔 비어 있고, 실행 시작
    요청 응답 이후 여기서 채운다. 이후 재개(resume)는 이 값으로 Agent thread 를 찾는다.
    """
    context.agent_thread_id = agent_thread_id
    await session.commit()
    await session.refresh(context)
    return context
