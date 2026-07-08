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
    expires_in: int = Field(description="티켓 유효 시간(초)")
