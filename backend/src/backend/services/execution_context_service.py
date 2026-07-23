"""Execution Context 발급·검증 비즈니스 로직.

계약 4.4·5장: Backend 는 모든 Agent Tool 요청에서 X-Execution-Context-Id 로 Context
존재·활성·만료·사용자 연결을 확인한다. 검증 실패는 Agent Tool 오류 envelope(D2)으로
번역되도록 `AgentToolError` 를 던진다. DB 접근은 repository 로 위임한다(계층 경계).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.agent_exceptions import AgentToolError
from ..core.load_environment_var import settings
from ..models.execution_context import ExecutionContext, ExecutionContextStatus
from ..repository.execution_context_repository import (
    create_execution_context,
    get_execution_context_by_id,
)
from ..schemas.execution_context import ResolvedExecutionContext
from ..utils.parsing import parse_uuid


async def issue_context(
    session: AsyncSession,
    user_id: UUID,
    chat_session_id: UUID,
    scopes: list[str],
    ttl_seconds: int | None = None,
    execution_timezone: str | None = None,
    agent_thread_id: str | None = None,
) -> ExecutionContext:
    """새 실행 Context 를 발급한다. 만료시각은 now + TTL 로 고정한다."""
    ttl = ttl_seconds if ttl_seconds is not None else settings.EXECUTION_CONTEXT_TTL_SECONDS
    tz = execution_timezone or settings.DEFAULT_EXECUTION_TIMEZONE
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
    return await create_execution_context(
        session,
        user_id=user_id,
        chat_session_id=chat_session_id,
        scopes=scopes,
        expires_at=expires_at,
        timezone=tz,
        agent_thread_id=agent_thread_id,
    )


def _to_resolved(context: ExecutionContext) -> ResolvedExecutionContext:
    return ResolvedExecutionContext(
        execution_context_id=context.id,
        user_id=context.user_id,
        chat_session_id=context.chat_session_id,
        agent_thread_id=context.agent_thread_id,
        scopes=list(context.scopes or []),
        timezone=context.timezone,
    )


async def resolve_context(session: AsyncSession, raw_context_id: str | None) -> ResolvedExecutionContext:
    """X-Execution-Context-Id 를 검증하고 사용자·스코프를 반환한다.

    - 형식오류/미존재: `INVALID_EXECUTION_CONTEXT` (401)
    - 만료(상태 EXPIRED 또는 expires_at 경과): `EXECUTION_CONTEXT_EXPIRED` (410)
    - 취소/종료: `INVALID_EXECUTION_CONTEXT` (401)
    """
    # 누락·형식오류는 INVALID_EXECUTION_CONTEXT.
    context_id = parse_uuid(raw_context_id, AgentToolError.invalid_execution_context)
    context = await get_execution_context_by_id(session, context_id)
    if context is None:
        raise AgentToolError.invalid_execution_context()

    if context.status is ExecutionContextStatus.EXPIRED:
        raise AgentToolError.execution_context_expired()
    if context.status is not ExecutionContextStatus.ACTIVE:
        # CANCELLED / COMPLETED: 더 이상 사용할 수 없는 Context.
        raise AgentToolError.invalid_execution_context()

    if context.expires_at <= datetime.now(timezone.utc):
        raise AgentToolError.execution_context_expired()

    return _to_resolved(context)
