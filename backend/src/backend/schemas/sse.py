from enum import Enum
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class AgentStreamEventType(str, Enum):
    STATUS = "status"
    TOKEN = "token"  # agent가 내뱉는 토큰 스트리밍
    TOOL_CALL = "tool_call"
    COMPONENT = "component"  # 결과/읽기 UI 카드 렌더(데이터는 metadata.ui.payload 인라인)
    # 일반 입력·선택 대기(UI-HITL 계약 1.4). 식별자는 metadata.input_request_id.
    NEED_INPUT = "need_input"
    NEED_APPROVAL = "need_approval"  # 승인 대기. approval_id(= confirmation_id) 사용
    # 추가 인증 대기(계약 1.4). 식별자는 metadata.auth_context_id.
    AUTHENTICATION_REQUIRED = "authentication_required"
    DONE = "done"
    ERROR = "error"
    BLOCKED = "blocked"  # 업무 차단 종료(workflow_failed). done/error 와 함께 terminal.


class AgentStreamEvent(BaseModel):
    event_type: AgentStreamEventType
    content: str
    approval_id: str | None = None
    metadata: dict | None = None


class SseTicketResponse(BaseModel):
    sse_session_id: UUID
    chat_session_id: UUID = Field(description="바인딩된 대화 세션 ID. connect 시 이 세션의 스트림을 구독한다.")
    expires_in: int = Field(description="티켓 유효 시간(초)")


class SseTicketContext(BaseModel):
    """티켓 소비(consume) 결과. connect 핸들러가 스트림 키를 유도하는 데 사용."""

    user_id: UUID
    chat_session_id: UUID


class AgentWebhookPayload(BaseModel):
    """Agent → 백엔드 웹훅(POST /webhooks/agent) 요청 규격.

    실제 Agent 또는 목 프로듀서가 이 규격으로 호출하면
    백엔드가 agent:stream:{chat_session_id} 로 XADD 한다.

    명칭 규약(계약점검 #2 결정): FE·BE 는 `approval_id`, Agent 는 `confirmation_id` 로 부른다.
    Agent 가 need_approval 웹훅에 top-level `confirmation_id` 를 보내므로 Backend 경계에서
    이를 `approval_id` 로 흡수한다(둘 중 어느 이름으로 와도 같은 필드로 받는다).
    """

    model_config = ConfigDict(populate_by_name=True)

    chat_session_id: UUID
    event_type: AgentStreamEventType
    content: str
    approval_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("approval_id", "confirmation_id"),
    )
    metadata: dict | None = None
