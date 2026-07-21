"""Execution Context 관련 DTO.

`ResolvedExecutionContext` 는 Agent Tool API 의존성이 X-Execution-Context-Id 를
검증한 뒤 라우터로 넘기는 최소 신원·권한 정보다. ORM 모델을 그대로 노출하지 않고
필요한 값만 전달한다(계층 경계 유지).
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class ResolvedExecutionContext(BaseModel):
    """검증이 끝난 실행 Context. 라우터·서비스는 여기서 사용자를 결정한다."""

    execution_context_id: UUID
    user_id: UUID
    chat_session_id: UUID
    agent_thread_id: str | None
    scopes: list[str]
    timezone: str

    def has_scope(self, scope: str) -> bool:
        """엔드포인트가 요구하는 스코프를 이 Context 가 보유하는지."""
        return scope in self.scopes
