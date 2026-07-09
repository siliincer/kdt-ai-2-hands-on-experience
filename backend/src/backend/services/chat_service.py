"""Chat 턴 오케스트레이션 (비즈니스 로직).

api(chat_api)는 얇게 두고, 세션 확정·메시지 저장·에이전트 호출은 여기서 처리한다.
DB 접근은 repository, 에이전트 구동은 driver(현재 mock)에 위임한다.
실제 Agent 연동 시 _trigger_* 부분만 Agent API 호출로 교체하면 된다.
"""

import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..repository.chat_repository import add_chat_message
from .chat_session_service import resolve_chat_session, verify_chat_session_owner
from .mock_agent_driver import run_after_approval, run_initial_turn


async def start_chat_turn(
    session: AsyncSession,
    user_id: UUID,
    chat_session_id: UUID | None,
    message: str,
) -> UUID:
    """사용자 메시지를 저장하고 에이전트 턴을 시작한다.

    DB 트랜잭션은 짧게(세션 확정 + user 메시지 저장)만 잡고,
    에이전트 진행은 백그라운드로 스트림(SSE)에 발행한 뒤 즉시 반환한다.
    """
    resolved_id = await resolve_chat_session(session, user_id, chat_session_id)
    await add_chat_message(session, resolved_id, "user", message)

    # TODO: 실제 Agent 연동 시 Agent API 호출로 교체
    asyncio.create_task(run_initial_turn(resolved_id, message))
    return resolved_id


async def resume_after_approval(
    session: AsyncSession,
    user_id: UUID,
    chat_session_id: UUID,
    approval_id: str,
    decision: str,
    args: dict | None,
) -> None:
    """confirm 카드(HITL) 승인/거절 → 에이전트 후속 턴을 재개한다."""
    await verify_chat_session_owner(session, user_id, chat_session_id)

    # TODO: 실제 Agent 연동 시 Agent 승인 API 호출로 교체
    asyncio.create_task(
        run_after_approval(chat_session_id, approval_id, decision, args)
    )
