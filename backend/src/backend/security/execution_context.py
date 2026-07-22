"""Agent Tool API 공통 의존성 — 서비스 인증 + Execution Context 해석.

라우터는 `Depends(get_agent_tool_context)` 하나로 (1) 서비스 토큰 검증과
(2) X-Execution-Context-Id 해석·검증을 모두 통과한 `ResolvedExecutionContext` 를 받는다.
스코프가 필요한 엔드포인트는 `require_scope("account:read")` 를 추가로 건다.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.agent_exceptions import AgentToolError
from ..core.request_context import bind_request_id
from ..db.postgres import get_db
from ..schemas.execution_context import ResolvedExecutionContext
from ..services.execution_context_service import resolve_context
from .agent_service_auth import verify_agent_service_token


async def get_agent_tool_context(
    _: None = Depends(verify_agent_service_token),
    # X-Request-Id 를 요청 스코프에 바인딩한다(로그 상관관계 전용, 계약 6장).
    # 값 자체는 여기서 쓰지 않고 로그·감사 기록이 ContextVar 로 꺼내 쓴다.
    _request_id: str = Depends(bind_request_id),
    x_execution_context_id: str | None = Header(
        default=None, alias="X-Execution-Context-Id"
    ),
    session: AsyncSession = Depends(get_db),
) -> ResolvedExecutionContext:
    """서비스 인증을 통과한 뒤 실행 Context 를 해석해 반환한다."""
    return await resolve_context(session, x_execution_context_id)


def require_scope(
    scope: str,
) -> Callable[
    [ResolvedExecutionContext], Coroutine[Any, Any, ResolvedExecutionContext]
]:
    """엔드포인트 필요 스코프를 강제하는 의존성 팩토리.

    사용 예: `ctx = Depends(require_scope("account:read"))`.
    스코프 미보유 시 INSUFFICIENT_SCOPE(403).
    """

    async def _dependency(
        context: ResolvedExecutionContext = Depends(get_agent_tool_context),
    ) -> ResolvedExecutionContext:
        if not context.has_scope(scope):
            raise AgentToolError.insufficient_scope()
        return context

    return _dependency
