import secrets
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import limiter
from ..core.load_environment_var import settings
from ..db.postgres import get_db
from ..db.redis import get_redis_stream
from ..schemas.response import CommonResponse
from ..schemas.sse import AgentStreamEvent, AgentStreamEventType, AgentWebhookPayload
from ..services.agent_stream_producer import publish_agent_event
from ..services.pending_input_service import register_pending_input_from_event
from ..utils.build_response import success_response

webhook_router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


def verify_agent_secret(x_agent_secret: str = Header(default="")) -> None:
    """Agent → 웹훅 호출 시 공유 시크릿을 상수시간 비교로 검증한다."""
    expected = settings.AGENT_WEBHOOK_SECRET.get_secret_value()
    if not secrets.compare_digest(x_agent_secret, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 Agent 웹훅 시크릿입니다.",
        )


def _parse_optional_uuid(raw: str | None) -> UUID | None:
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None


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
    x_execution_context_id: str = Header(default=""),
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
            execution_context_id=_parse_optional_uuid(x_execution_context_id),
        )

    event = AgentStreamEvent(
        event_type=payload.event_type,
        content=payload.content,
        approval_id=payload.approval_id,
        metadata=payload.metadata,
    )
    message_id = await publish_agent_event(redis_stream, payload.chat_session_id, event)
    return success_response(
        message="Agent 이벤트가 스트림에 발행되었습니다.",
        data={"message_id": message_id},
    )
