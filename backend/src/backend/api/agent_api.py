# api/agent_api.py
"""에이전트 채팅 프록시 API.

frontend → backend(/api/v1/agent/chat) → agent(/chat) 경로의 게이트웨이 계층.
에이전트 응답을 CommonResponse 성공 봉투(data 필드)에 담아 반환한다.
"""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..schemas.response import CommonResponse
from ..services.agent_client import call_agent_chat
from ..utils.build_response import success_response

agent_router = APIRouter(prefix="/agent", tags=["Agent"])


class AgentChatRequest(BaseModel):
    """채팅 요청 (agent 서비스 ChatRequest와 동일 계약)."""

    message: str = Field(min_length=1, max_length=2000, description="사용자 발화")
    thread_id: str | None = Field(
        None, description="직전 응답이 waiting_input일 때 회송하는 스레드 id"
    )
    user_id: str = Field("user_001", description="사용자 id")


class AgentChatData(BaseModel):
    """채팅 응답 데이터 (agent 서비스 ChatResponse와 동일 계약)."""

    reply: str
    status: Literal["completed", "waiting_input", "blocked", "no_match", "failed"]
    thread_id: str
    prompt_for: str | None = None
    # waiting_input일 때 agent가 내려주는 구조화 UI 힌트 (opaque 전달)
    ui: dict | None = None


@agent_router.post("/chat", response_model=CommonResponse[AgentChatData])
async def chat_with_agent(request: AgentChatRequest):
    data = await call_agent_chat(request.model_dump())
    return success_response(message="에이전트 응답을 가져왔습니다.", data=data)
