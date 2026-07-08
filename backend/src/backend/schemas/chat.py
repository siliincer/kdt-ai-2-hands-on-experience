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
    APPROVE = "approve"
    REJECT = "reject"


class ApproveRequest(BaseModel):
    """POST /api/v1/agent/approve — confirm 카드(HITL) 승인/거절."""

    chat_session_id: UUID
    approval_id: str
    decision: ApprovalDecision
    args: dict | None = Field(
        default=None,
        description="사용자가 confirm 카드에서 수정한 값(예: 송금 파라미터).",
    )
