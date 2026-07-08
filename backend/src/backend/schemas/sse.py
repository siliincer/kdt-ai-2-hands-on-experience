from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class AgentStreamEventType(str, Enum):
    STATUS = "status"
    TOKEN = "token"
    TOOL_CALL = "tool_call"
    NEED_APPROVAL = "need_approval"
    DONE = "done"
    ERROR = "error"


class AgentStreamEvent(BaseModel):
    event_type: AgentStreamEventType
    content: str
    approval_id: str | None = None
    metadata: dict | None = None


class SseTicketResponse(BaseModel):
    sse_session_id: UUID
    chat_session_id: UUID = Field(
        description="바인딩된 대화 세션 ID. connect 시 이 세션의 스트림을 구독한다."
    )
    expires_in: int = Field(description="티켓 유효 시간(초)")


class SseTicketContext(BaseModel):
    """티켓 소비(consume) 결과. connect 핸들러가 스트림 키를 유도하는 데 사용."""

    user_id: UUID
    chat_session_id: UUID


class AgentWebhookPayload(BaseModel):
    """Agent → 백엔드 웹훅(POST /webhooks/agent) 요청 규격.

    실제 Agent 또는 목 프로듀서가 이 규격으로 호출하면
    백엔드가 agent:stream:{chat_session_id} 로 XADD 한다.
    """

    chat_session_id: UUID
    event_type: AgentStreamEventType
    content: str
    approval_id: str | None = None
    metadata: dict | None = None
