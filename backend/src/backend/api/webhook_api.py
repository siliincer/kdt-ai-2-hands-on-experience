import secrets

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Header, HTTPException, status

from ..core.config import limiter
from ..core.load_environment_var import settings
from ..db.redis import get_redis_stream
from ..schemas.response import CommonResponse
from ..schemas.sse import AgentStreamEvent, AgentWebhookPayload
from ..services.agent_stream_producer import publish_agent_event
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


@webhook_router.post(
    "/agent",
    response_model=CommonResponse[dict],
    dependencies=[Depends(verify_agent_secret)],
)
@limiter.exempt
async def receive_agent_webhook(
    payload: AgentWebhookPayload,
    redis_stream: aioredis.Redis = Depends(get_redis_stream),
):
    """Agent(또는 목 프로듀서)가 진행 이벤트를 보내면
    agent:stream:{chat_session_id} 스트림으로 XADD 하여 SSE로 중계되게 한다."""
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
