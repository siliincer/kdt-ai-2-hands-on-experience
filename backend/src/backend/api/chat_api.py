from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.postgres import get_db
from ..models.user import User
from ..schemas.chat import (
    AgentAuthenticateRequest,
    AgentInputRequest,
    ApproveRequest,
    ChatRequest,
    ChatResponse,
)
from ..schemas.response import CommonResponse
from ..security.jwt import get_current_user
from ..services.chat_service import (
    authenticate_and_resume,
    resume_after_approval,
    resume_after_input,
    start_chat_turn,
)
from ..utils.build_response import success_response

chat_router = APIRouter(tags=["Chat"])


@chat_router.post("/chat", response_model=CommonResponse[ChatResponse])
async def send_chat_message(
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """사용자 메시지를 받아 에이전트 턴을 시작한다(진행은 SSE)."""
    chat_session_id = await start_chat_turn(session, current_user.id, payload.chat_session_id, payload.message)
    return success_response(
        message="메시지가 접수되었습니다.",
        data=ChatResponse(chat_session_id=chat_session_id),
    )


@chat_router.post("/agent/approve", response_model=CommonResponse[dict])
async def approve_agent_action(
    payload: ApproveRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """confirm 카드(HITL) 승인/거절 → 에이전트 후속 턴을 재개한다."""
    await resume_after_approval(
        session,
        current_user.id,
        payload.chat_session_id,
        payload.approval_id,
        payload.decision.value,
        payload.args,
        payload.component,
        payload.change_target,
    )
    return success_response(
        message="승인 결과가 접수되었습니다.",
        data={"decision": payload.decision.value},
    )


@chat_router.post("/agent/input", response_model=CommonResponse[dict])
async def submit_agent_input(
    payload: AgentInputRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """일반 입력·선택 대기(HITL) 회신 → 에이전트 후속 턴을 재개한다(계약 1.5)."""
    await resume_after_input(
        session,
        current_user.id,
        payload.chat_session_id,
        payload.input_request_id,
        payload.value,
    )
    return success_response(
        message="입력이 접수되었습니다.",
        data={"input_request_id": payload.input_request_id},
    )


@chat_router.post("/agent/authenticate", response_model=CommonResponse[dict])
async def authenticate_agent_action(
    payload: AgentAuthenticateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """추가 인증(비밀번호 재확인) → 검증 후 에이전트 후속 턴을 재개한다(계약 3.8)."""
    auth_status = await authenticate_and_resume(
        session,
        current_user.id,
        payload.chat_session_id,
        payload.auth_context_id,
        payload.password,
    )
    return success_response(
        message="인증 결과가 접수되었습니다.",
        data={"auth_status": auth_status},
    )
