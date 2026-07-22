"""Chat 턴 오케스트레이션 (비즈니스 로직).

api(chat_api)는 얇게 두고, 세션 확정·메시지 저장·에이전트 호출은 여기서 처리한다.
DB 접근은 repository, 에이전트 구동은 driver(현재 mock)에 위임한다.
실제 Agent 연동 시 _trigger_* 부분만 Agent API 호출로 교체하면 된다.
"""

import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.security import verify_password
from ..models.auth_context import AuthContextStatus
from ..models.confirmation import ConfirmationStatus
from ..repository.auth_context_repository import (
    get_auth_context_by_id,
    set_auth_context_status,
)
from ..repository.chat_repository import add_chat_message
from ..repository.confirmation_repository import get_confirmation_by_id
from ..repository.user_repository import get_user_by_id
from ..utils.constants import (
    SCOPE_ACCOUNT_READ,
    SCOPE_SETTINGS_WRITE,
    SCOPE_TRANSFER_REQUEST,
)
from . import auth_context_service, confirmation_service
from .chat_session_service import resolve_chat_session, verify_chat_session_owner
from .execution_context_service import issue_context
from .mock_agent_driver import (
    run_after_approval,
    run_after_auth,
    run_after_input,
    run_initial_turn,
)
from .pending_input_service import consume_pending_input

# 채팅 턴에 발급하는 Execution Context 의 기본 스코프(계약 5장). 워크플로우가 정해지기
# 전이라 조회·이체·설정을 모두 허용한다(실 Agent 연동 시 워크플로우별로 좁힐 수 있음).
_CHAT_SCOPES = [SCOPE_ACCOUNT_READ, SCOPE_TRANSFER_REQUEST, SCOPE_SETTINGS_WRITE]

# confirm_modal(설정 변경·송금)은 실제 Confirmation 생명주기에 연결한다. 레거시 자동이체
# confirm 은 mock approval_id 를 쓰므로 이 집합에 포함하지 않는다.
_CONFIRMATION_COMPONENTS = frozenset(
    {"account_alias", "default_account", "external_transfer", "internal_transfer"}
)


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
    context = await issue_context(
        session,
        user_id=user_id,
        chat_session_id=resolved_id,
        scopes=_CHAT_SCOPES,
        agent_thread_id=agent_thread_id,
    )

    # TODO(BE): 실제 Agent 연동 시 Agent API 호출로 교체.
    # execution_context_id·agent_thread_id 를 넘겨 need_input 대기 행이 이 턴의
    # 실행 Context 에 연결되게 한다(계약 1.3).
    asyncio.create_task(
        run_initial_turn(
            resolved_id,
            message,
            execution_context_id=context.id,
            agent_thread_id=agent_thread_id,
        )
    )
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
    """confirm 카드(HITL) 승인/거절/수정 → 에이전트 후속 턴을 재개한다."""
    await verify_chat_session_owner(session, user_id, chat_session_id)

    # 설정·송금 confirm_modal 은 실제 Confirmation 생명주기에 반영한다(Stage 7).
    # 재개 전에 승인/폐기해 두면, mock 드라이버는 결과·인증 이벤트만 발행한다.
    if component in _CONFIRMATION_COMPONENTS:
        await _apply_setting_confirmation(session, user_id, approval_id, decision)

    # TODO(BE): 실제 Agent 연동 시 Agent 승인 API 호출로 교체
    # user_id 를 넘겨 승인 시 계정계 실이체(transfer_service)를 태운다(Phase 2).
    asyncio.create_task(
        run_after_approval(
            chat_session_id, approval_id, decision, args, component, user_id
        )
    )


async def _apply_setting_confirmation(
    session: AsyncSession,
    user_id: UUID,
    confirmation_id: str,
    decision: str,
) -> None:
    """설정 confirm_modal 결과를 실제 Confirmation 에 반영한다(승인 생명주기).

    검증 실패는 재개하지 않고 HTTPException 으로 같은 UI 에서 처리한다. 다른 사용자의
    Confirmation 은 존재를 숨기고 404 로 응답한다(정보 노출 방지).
    """
    try:
        conf_uuid = UUID(confirmation_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="확인 요청을 찾을 수 없습니다.",
        )
    confirmation = await get_confirmation_by_id(session, conf_uuid)
    now = datetime.now(timezone.utc)
    if confirmation is None or confirmation.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="확인 요청을 찾을 수 없습니다.",
        )
    if (
        confirmation.status is ConfirmationStatus.EXPIRED
        or confirmation.expires_at <= now
    ):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="확인 요청이 만료되었습니다. 다시 시도해 주세요.",
        )
    if confirmation.status is not ConfirmationStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 처리된 확인 요청입니다.",
        )

    if decision == "approve":
        await confirmation_service.approve(session, confirmation)
    else:
        # cancelled / change_requested: 기존 Confirmation 을 재사용 불가 처리(계약 7.6).
        await confirmation_service.invalidate(session, confirmation)


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

    # TODO(BE): 실제 Agent 연동 시 Agent 재개 API 호출로 교체.
    # execution_context_id 를 넘겨 다음 단계(예: 별칭 Confirmation 생성)가 이 턴의
    # 실행 Context 에 묶이게 한다.
    asyncio.create_task(
        run_after_input(
            chat_session_id,
            pending.ui_contract_id,
            value,
            execution_context_id=pending.execution_context_id,
        )
    )


async def authenticate_and_resume(
    session: AsyncSession,
    user_id: UUID,
    chat_session_id: UUID,
    auth_context_id: str,
    password: str,
) -> str:
    """추가 인증(비밀번호 재확인) → 검증 후 에이전트를 재개한다(계약 3.8·7.2).

    인증 원문(비밀번호)은 Backend 까지만 오고 Agent 로 전달하지 않는다. Backend 가
    검증한 결과 상태(verified/failed)만 재개에 사용한다. 반환값은 결과 상태다.
    검증 실패(세션·인증 상태)는 HTTPException 으로 같은 UI 에서 처리한다.
    """
    await verify_chat_session_owner(session, user_id, chat_session_id)

    try:
        auth_uuid = UUID(auth_context_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="인증 요청을 찾을 수 없습니다.",
        )
    auth_context = await get_auth_context_by_id(session, auth_uuid)
    now = datetime.now(timezone.utc)
    if auth_context is None or auth_context.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="인증 요청을 찾을 수 없습니다.",
        )
    if (
        auth_context.status is AuthContextStatus.EXPIRED
        or auth_context.expires_at <= now
    ):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="인증 요청이 만료되었습니다. 다시 시도해 주세요.",
        )
    if auth_context.status is not AuthContextStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 처리된 인증 요청입니다.",
        )

    user = await get_user_by_id(session, str(user_id))
    verified = bool(user and password and verify_password(password, user.password_hash))

    if verified:
        await auth_context_service.mark_verified(session, auth_context)
        auth_status = "verified"
    else:
        await set_auth_context_status(session, auth_context, AuthContextStatus.FAILED)
        auth_status = "failed"

    # TODO(BE): 실제 Agent 연동 시 Agent 재개 API 호출로 교체.
    asyncio.create_task(run_after_auth(chat_session_id, auth_status))
    return auth_status
