from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """POST /api/v1/chat — 사용자 메시지 전송."""

    chat_session_id: UUID | None = Field(
        default=None,
        description="이어갈 대화 세션. 생략 시 새 세션을 만든다.",
    )
    message: str = Field(min_length=1, description="사용자 자연어 메시지")


class ChatResponse(BaseModel):
    """즉시 반환. 진행 상황은 SSE(agent:stream:{chat_session_id})로 스트리밍된다."""

    chat_session_id: UUID


class ApprovalDecision(str, Enum):
    # 레거시 송금/자동이체 confirm 은 approve/reject 를 쓴다.
    APPROVE = "approve"
    REJECT = "reject"
    # confirm_modal(UI-HITL 계약 3.7): 승인/수정/취소.
    CHANGE_REQUESTED = "change_requested"
    CANCELLED = "cancelled"


class ApproveRequest(BaseModel):
    """POST /api/v1/agent/approve — confirm 카드(HITL) 승인/거절/수정."""

    chat_session_id: UUID
    approval_id: str
    decision: ApprovalDecision
    args: dict | None = Field(
        default=None,
        description="사용자가 confirm 카드에서 수정한 값(예: 송금 파라미터).",
    )
    component: str | None = Field(
        default=None,
        description="어떤 confirm 인지(transfer/autotransfer/account_alias 등).",
    )
    change_target: str | None = Field(
        default=None,
        description="change_requested 일 때 수정 대상(계약 3.7, 예: alias).",
    )


class AgentInputRequest(BaseModel):
    """POST /api/v1/agent/input — 일반 입력·선택 대기 회신(UI-HITL 계약 1.5).

    승인(approve)과 구분되는 입력 제출이다. `input_request_id` 로 대기 행을 매칭하고
    `value` 는 UI 계약별 `*_outcome` 필드를 포함한다(예: account_selection_outcome).
    """

    chat_session_id: UUID
    input_request_id: str = Field(
        min_length=1, description="Agent 가 발급한 입력 요청 id"
    )
    value: dict = Field(description="UI 계약별 제출값(outcome 필드 포함)")
