"""Agent Service FastAPI 진입점.

LangGraph 기반 금융 에이전트를 HTTP로 노출한다.
docker-compose/nginx가 기대하는 진입점: agent.main:app (포트 8001).
"""

from __future__ import annotations

from fastapi import FastAPI

from agent.schemas import ChatRequest, ChatResponse
from agent.service import run_chat

app = FastAPI(title="RealFinancial Agent", version="0.1.0")


@app.get("/health")
def health() -> dict:
    """컨테이너/게이트웨이 헬스체크용."""
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """사용자 발화 한 턴을 처리한다.

    그래프가 전부 동기 코드라 sync def로 두어 FastAPI가
    threadpool에서 실행하게 한다 (이벤트 루프 블로킹 방지).
    """
    result = run_chat(request.message, request.user_id, request.thread_id)
    return ChatResponse(**result)
