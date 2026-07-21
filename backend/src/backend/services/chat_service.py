"""Chat 턴 오케스트레이션 (비즈니스 로직).

api(chat_api)는 얇게 두고, 세션 확정·메시지 저장·에이전트 호출은 여기서 처리한다.
DB 접근은 repository, 에이전트 구동은 실 Agent 내부 실행 API(agent_client)에 위임한다.

계약(agent-integration-interface §2): Backend 는 재개 전에 값을 검증(소유권·활성
pending_input·Confirmation/AuthContext 상태)한 뒤, 검증된 값으로 Agent Workflow 를
실행/재개한다. Agent 는 빠른 202 만 돌려주고 진행 결과는 Webhook 으로 발행한다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.security import verify_password
from ..models.auth_context import AuthContextStatus
from ..models.confirmation import Confirmation, ConfirmationStatus
from ..repository.auth_context_repository import (
    get_auth_context_by_id,
    set_auth_context_status,
)
from ..repository.chat_repository import add_chat_message
from ..repository.confirmation_repository import get_confirmation_by_id
from ..repository.execution_context_repository import (
    get_execution_context_by_id,
    set_agent_thread_id,
)
from ..repository.user_repository import get_user_by_id
from ..utils.constants import (
    SCOPE_ACCOUNT_READ,
    SCOPE_SETTINGS_WRITE,
    SCOPE_TRANSFER_REQUEST,
)
from . import auth_context_service, confirmation_service
from .agent_client import get_agent_client
from .chat_session_service import resolve_chat_session, verify_chat_session_owner
from .execution_context_service import issue_context
from .pending_input_service import consume_pending_input

# 채팅 턴에 발급하는 Execution Context 의 기본 스코프(계약 5장). 워크플로우가 정해지기
# 전이라 조회·이체·설정을 모두 허용한다(실 Agent 연동 시 워크플로우별로 좁힐 수 있음).
_CHAT_SCOPES = [SCOPE_ACCOUNT_READ, SCOPE_TRANSFER_REQUEST, SCOPE_SETTINGS_WRITE]

# confirm_modal(설정 변경·송금)은 실제 Confirmation 생명주기에 연결한다. 승인 시 approve,
# 취소/수정 시 invalidate 해 두면 Agent 의 agent-tools Execute 가 상태를 확인해 진행한다.
_CONFIRMATION_COMPONENTS = frozenset({"account_alias", "default_account", "external_transfer", "internal_transfer"})


def _new_request_id(kind: str) -> str:
    """실행/재개 요청 상관관계용 request_id 를 생성한다(로그 추적 전용, 계약 9장)."""
    return f"req_{kind}_{uuid4().hex}"


async def _resolve_agent_thread_id(session: AsyncSession, execution_context_id: UUID | None) -> tuple[str, UUID]:
    """재개 대상 Agent thread 를 실행 Context 에서 찾는다.

    thread 발급 주체는 Agent 이고, 실행 시작 응답으로 받은 값을 Context 에 연결해 둔다.
    Context 나 thread 가 없으면(정상 흐름에선 발생하지 않음) 재개할 수 없다.
    반환: (agent_thread_id, execution_context_id).
    """
    if execution_context_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="재개할 실행을 찾을 수 없습니다.",
        )
    context = await get_execution_context_by_id(session, execution_context_id)
    if context is None or not context.agent_thread_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="재개할 실행을 찾을 수 없습니다.",
        )
    return context.agent_thread_id, execution_context_id


async def start_chat_turn(
    session: AsyncSession,
    user_id: UUID,
    chat_session_id: UUID | None,
    message: str,
) -> UUID:
    """사용자 메시지를 저장하고 에이전트 턴을 시작한다.

    Execution Context 를 먼저 발급하되 agent_thread_id 는 비워 둔다(발급 주체가 Agent).
    실행 시작 요청(빠른 202)의 응답으로 받은 agent_thread_id 를 Context 에 연결한 뒤
    반환한다. 진행 결과는 Agent 가 Webhook 으로 발행한다.
    """
    resolved_id = await resolve_chat_session(session, user_id, chat_session_id)
    await add_chat_message(session, resolved_id, "user", message)

    # thread 발급 주체는 Agent 이므로 이 시점엔 agent_thread_id 를 넣지 않는다(계약 1.3).
    context = await issue_context(
        session,
        user_id=user_id,
        chat_session_id=resolved_id,
        scopes=_CHAT_SCOPES,
    )

    request_id = _new_request_id("start")
    agent_thread_id = await get_agent_client().start_execution(
        request_id=request_id,
        chat_session_id=str(resolved_id),
        execution_context_id=str(context.id),
        message=message,
    )
    # Agent 가 발급한 thread 를 Context 에 연결한다. 이후 재개는 이 값으로 thread 를 찾는다.
    await set_agent_thread_id(session, context, agent_thread_id)
    return resolved_id


async def resume_after_approval(
    session: AsyncSession,
    user_id: UUID,
    chat_session_id: UUID,
    approval_id: str,
    decision: str,
    args: dict | None,
    component: str | None = None,
    change_target: str | None = None,
) -> None:
    """confirm 카드(HITL) 승인/거절/수정 → 에이전트 후속 턴을 재개한다.

    실제 Confirmation 을 승인/폐기한 뒤(재개 전 검증 계약), 그 Confirmation 의 실행
    Context 에 연결된 Agent thread 를 재개한다. 승인이면 Agent 의 Execute 가 EXECUTED 로
    전이시키고, 취소/수정이면 Agent 가 그 결과에 맞춰 마무리한다.
    """
    await verify_chat_session_owner(session, user_id, chat_session_id)

    confirmation = await _load_owned_confirmation(session, user_id, approval_id)
    # 설정·송금 confirm_modal 은 실제 Confirmation 생명주기에 반영한다(Stage 7).
    if component in _CONFIRMATION_COMPONENTS:
        await _apply_confirmation_decision(session, confirmation, decision)

    agent_thread_id, execution_context_id = await _resolve_agent_thread_id(session, confirmation.execution_context_id)
    await get_agent_client().resume_approval(
        agent_thread_id=agent_thread_id,
        request_id=_new_request_id("resume"),
        chat_session_id=str(chat_session_id),
        execution_context_id=str(execution_context_id),
        confirmation_id=approval_id,
        decision=decision,
        change_target=change_target,
    )


async def _load_owned_confirmation(
    session: AsyncSession,
    user_id: UUID,
    confirmation_id: str,
) -> Confirmation:
    """approval_id 로 본인 소유 Confirmation 을 로드·검증한다.

    다른 사용자의 Confirmation 은 존재를 숨기고 404 로 응답한다(정보 노출 방지).
    만료·이미 처리됨은 각각 410/409 로 같은 UI 에서 처리한다.
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
    if confirmation.status is ConfirmationStatus.EXPIRED or confirmation.expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="확인 요청이 만료되었습니다. 다시 시도해 주세요.",
        )
    if confirmation.status is not ConfirmationStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 처리된 확인 요청입니다.",
        )
    return confirmation


async def _apply_confirmation_decision(
    session: AsyncSession,
    confirmation: Confirmation,
    decision: str,
) -> None:
    """검증된 Confirmation 에 승인 결과를 반영한다(승인 생명주기)."""
    if decision == "approve":
        await confirmation_service.approve(session, confirmation)
    else:
        # cancelled / change_requested / reject: 재사용 불가 처리(계약 7.6).
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

    agent_thread_id, execution_context_id = await _resolve_agent_thread_id(session, pending.execution_context_id)
    await get_agent_client().resume_input(
        agent_thread_id=agent_thread_id,
        request_id=_new_request_id("resume"),
        chat_session_id=str(chat_session_id),
        execution_context_id=str(execution_context_id),
        input_request_id=input_request_id,
        value=value,
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
    if auth_context.status is AuthContextStatus.EXPIRED or auth_context.expires_at <= now:
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

    # 인증은 Confirmation 에 딸린 추가 관문이다. auth_context → confirmation → 실행
    # Context 로 Agent thread 를 찾아 재개한다.
    execution_context_id = await _resolve_execution_context_for_auth(session, auth_context.confirmation_id)
    agent_thread_id, resolved_ctx_id = await _resolve_agent_thread_id(session, execution_context_id)
    await get_agent_client().resume_authentication(
        agent_thread_id=agent_thread_id,
        request_id=_new_request_id("resume"),
        chat_session_id=str(chat_session_id),
        execution_context_id=str(resolved_ctx_id),
        auth_context_id=auth_context_id,
        auth_status=auth_status,
    )
    return auth_status


async def _resolve_execution_context_for_auth(session: AsyncSession, confirmation_id: UUID) -> UUID | None:
    """auth_context 가 가리키는 Confirmation 의 실행 Context id 를 찾는다."""
    confirmation: Confirmation | None = await get_confirmation_by_id(session, confirmation_id)
    if confirmation is None:
        return None
    return confirmation.execution_context_id
