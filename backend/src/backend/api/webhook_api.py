import logging
import secrets
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import limiter
from ..core.load_environment_var import settings
from ..core.request_context import bind_request_id
from ..db.postgres import get_db
from ..db.redis import get_redis_stream
from ..schemas.response import CommonResponse
from ..schemas.sse import AgentStreamEvent, AgentStreamEventType, AgentWebhookPayload
from ..services.agent_stream_producer import publish_agent_event
from ..services.pending_input_service import register_pending_input_from_event
from ..utils.build_response import success_response

logger = logging.getLogger(__name__)

webhook_router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


def verify_agent_secret(x_agent_secret: str = Header(default="")) -> None:
    """Agent → 웹훅 호출 시 공유 시크릿을 상수시간 비교로 검증한다."""
    expected = settings.AGENT_WEBHOOK_SECRET.get_secret_value()
    if not secrets.compare_digest(x_agent_secret, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 Agent 웹훅 시크릿입니다.",
        )


def require_execution_context_id(
    x_execution_context_id: str = Header(default=""),
) -> UUID:
    """X-Execution-Context-Id 를 필수로 검증한다(계약: 실 Agent 연동 시 필수 전환).

    Agent Webhook 클라이언트는 모든 이벤트에 이 헤더를 붙이므로, 누락·형식오류는
    잘못된 요청(400)으로 거절한다. need_input 의 pending_input 연결에도 이 값을 쓴다.
    """
    if not x_execution_context_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Execution-Context-Id 헤더가 필요합니다.",
        )
    try:
        return UUID(x_execution_context_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Execution-Context-Id 형식이 올바르지 않습니다.",
        )


@webhook_router.post(
    "/agent",
    response_model=CommonResponse[dict],
    dependencies=[Depends(verify_agent_secret)],
)
@limiter.exempt
async def receive_agent_webhook(
    payload: AgentWebhookPayload,
    redis_stream: aioredis.Redis = Depends(get_redis_stream),
    session: AsyncSession = Depends(get_db),
    execution_context_id: UUID = Depends(require_execution_context_id),
    # X-Request-Id: Agent 로그와 대조하기 위한 추적 id(중복 방지 용도가 아니다).
    request_id: str = Depends(bind_request_id),
):
    """Agent(또는 목 프로듀서)가 진행 이벤트를 보내면
    agent:stream:{chat_session_id} 스트림으로 XADD 하여 SSE로 중계되게 한다.

    need_input 이벤트는 SSE 로 흘리기 전에 대기 행(pending_input)을 먼저 영속화한다.
    (FE 가 need_input 을 받고 즉시 제출해도 대기 행이 존재하도록 순서를 보장한다.)
    """
    # need_input 은 SSE 발행보다 먼저 대기 행을 만든다(계약 1.4·1.5, 제출 경쟁 방지).
    if payload.event_type is AgentStreamEventType.NEED_INPUT:
        await register_pending_input_from_event(
            session,
            chat_session_id=payload.chat_session_id,
            metadata=payload.metadata,
            execution_context_id=execution_context_id,
        )

    event = AgentStreamEvent(
        event_type=payload.event_type,
        content=payload.content,
        approval_id=payload.approval_id,
        metadata=payload.metadata,
    )
    message_id = await publish_agent_event(redis_stream, payload.chat_session_id, event)
    # Agent 로그의 같은 request_id 로 어떤 Webhook 이벤트가 처리됐는지 대조한다.
    logger.info(
        "agent webhook handled request_id=%s event_type=%s chat_session_id=%s message_id=%s",
        request_id,
        payload.event_type.value,
        payload.chat_session_id,
        message_id,
    )
    return success_response(
        message="Agent 이벤트가 스트림에 발행되었습니다.",
        data={"message_id": message_id},
    )
