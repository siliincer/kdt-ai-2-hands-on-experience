"""Chat 턴 오케스트레이션 (비즈니스 로직).

api(chat_api)는 얇게 두고, 세션 확정·메시지 저장·에이전트 호출은 여기서 처리한다.
DB 접근은 repository, 에이전트 구동은 driver(현재 mock)에 위임한다.
실제 Agent 연동 시 _trigger_* 부분만 Agent API 호출로 교체하면 된다.
"""

import asyncio
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from ..repository.chat_repository import add_chat_message
from ..utils.constants import (
    SCOPE_ACCOUNT_READ,
    SCOPE_SETTINGS_WRITE,
    SCOPE_TRANSFER_REQUEST,
)
from .chat_session_service import resolve_chat_session, verify_chat_session_owner
from .execution_context_service import issue_context
from .mock_agent_driver import run_after_approval, run_after_input, run_initial_turn
from .pending_input_service import consume_pending_input

# 채팅 턴에 발급하는 Execution Context 의 기본 스코프(계약 5장). 워크플로우가 정해지기
# 전이라 조회·이체·설정을 모두 허용한다(실 Agent 연동 시 워크플로우별로 좁힐 수 있음).
_CHAT_SCOPES = [SCOPE_ACCOUNT_READ, SCOPE_TRANSFER_REQUEST, SCOPE_SETTINGS_WRITE]


async def start_chat_turn(
    session: AsyncSession,
    user_id: UUID,
    chat_session_id: UUID | None,
    message: str,
) -> UUID:
    """사용자 메시지를 저장하고 에이전트 턴을 시작한다.

    DB 트랜잭션은 짧게(세션 확정 + user 메시지 저장 + Execution Context 발급)만 잡고,
    에이전트 진행은 백그라운드로 스트림(SSE)에 발행한 뒤 즉시 반환한다.
    """
    resolved_id = await resolve_chat_session(session, user_id, chat_session_id)
    await add_chat_message(session, resolved_id, "user", message)

    # Stage 7 기반: 이 턴의 실행 Context 를 발급해 사용자·세션·thread 를 연결한다.
    # TODO(BE): 세션당 활성 Context 재사용(현재는 턴마다 발급). 실 Agent 연동 시 정리.
    agent_thread_id = uuid4().hex
    await issue_context(
        session,
        user_id=user_id,
        chat_session_id=resolved_id,
        scopes=_CHAT_SCOPES,
        agent_thread_id=agent_thread_id,
    )

    # TODO(BE): 실제 Agent 연동 시 Agent API 호출로 교체
    asyncio.create_task(run_initial_turn(resolved_id, message))
    return resolved_id


async def resume_after_approval(
    session: AsyncSession,
    user_id: UUID,
    chat_session_id: UUID,
    approval_id: str,
    decision: str,
    args: dict | None,
    component: str | None = None,
) -> None:
    """confirm 카드(HITL) 승인/거절 → 에이전트 후속 턴을 재개한다."""
    await verify_chat_session_owner(session, user_id, chat_session_id)

    # TODO(BE): 실제 Agent 연동 시 Agent 승인 API 호출로 교체
    # user_id 를 넘겨 승인 시 계정계 실이체(transfer_service)를 태운다(Phase 2).
    asyncio.create_task(
        run_after_approval(
            chat_session_id, approval_id, decision, args, component, user_id
        )
    )


async def resume_after_input(
    session: AsyncSession,
    user_id: UUID,
    chat_session_id: UUID,
    input_request_id: str,
    value: dict,
) -> None:
    """일반 입력·선택 대기 회신(HITL) → 에이전트 후속 턴을 재개한다(계약 1.5).

    소유권과 대기 행(pending_input)을 검증·소비한 뒤에만 재개한다. 검증 실패는
    consume_pending_input 이 HTTPException 으로 던져 같은 UI 에서 처리된다(재개 없음).
    """
    await verify_chat_session_owner(session, user_id, chat_session_id)
    pending = await consume_pending_input(session, chat_session_id, input_request_id)

    # TODO(BE): 실제 Agent 연동 시 Agent 재개 API 호출로 교체
    asyncio.create_task(run_after_input(chat_session_id, pending.ui_contract_id, value))
