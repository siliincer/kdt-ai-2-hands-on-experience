"""Agent Service FastAPI 진입점.

LangGraph 기반 금융 에이전트를 HTTP로 노출한다.
docker-compose/nginx가 기대하는 진입점: agent.main:app (포트 8001).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import AsyncIterator, Protocol

from fastapi import FastAPI

from agent.application_runtime import create_agent_runtime_resources
from agent.internal_execution_api import router as internal_execution_router
from agent.runtime import ExecutionRuntime
from agent.schemas import ChatRequest, ChatResponse
from agent.service import run_chat


class RuntimeResources(Protocol):
    """FastAPI lifespan이 초기화하고 종료하는 Runtime 자원 경계."""

    @property
    def execution_runtime(self) -> ExecutionRuntime: ...

    async def aclose(self) -> None: ...


RuntimeResourcesFactory = Callable[[], Awaitable[RuntimeResources]]


def create_app(
    runtime_resources_factory: RuntimeResourcesFactory = create_agent_runtime_resources,
) -> FastAPI:
    """공통 Execution Runtime을 lifespan에 연결한 FastAPI 앱을 만든다."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        resources = await runtime_resources_factory()
        application.state.execution_runtime = resources.execution_runtime
        application.state.runtime_resources = resources
        try:
            yield
        finally:
            await resources.aclose()

    application = FastAPI(
        title="RealFinancial Agent",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.include_router(internal_execution_router)

    @application.get("/health")
    def health() -> dict[str, str]:
        """컨테이너와 게이트웨이가 Runtime 준비 상태를 확인한다."""

        return {"status": "ok"}

    @application.post("/chat", response_model=ChatResponse)
    def chat(request: ChatRequest) -> ChatResponse:
        """기존 채팅 API 호환 경로를 처리한다."""

        result = run_chat(request.message, request.user_id, request.thread_id)
        return ChatResponse(**result)

    return application


app = create_app()
