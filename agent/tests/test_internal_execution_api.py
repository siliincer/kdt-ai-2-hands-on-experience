"""Backend 전용 Agent 실행 시작·Resume API 계약 테스트."""

from __future__ import annotations

from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.internal_execution_api import router
from agent.runtime import (
    ExecutionAccepted,
    ExecutionResumeAccepted,
    ExecutionResumeRequest,
    ExecutionRunResult,
    ExecutionRuntime,
    ExecutionRuntimeError,
    ExecutionStartRequest,
)


class StubExecutionRuntime:
    def __init__(self) -> None:
        self.start_requests: list[ExecutionStartRequest] = []
        self.resume_requests: list[tuple[str, ExecutionResumeRequest]] = []
        self.started_threads: list[str] = []
        self.resumed_requests: list[tuple[str, str]] = []
        self.replay_start = False
        self.replay_resume = False
        self.resume_error: Exception | None = None

    def accept_start(self, request: ExecutionStartRequest) -> ExecutionAccepted:
        self.start_requests.append(request)
        return ExecutionAccepted(
            agent_thread_id="thread_123",
            replayed=self.replay_start,
        )

    async def run_accepted(self, agent_thread_id: str) -> ExecutionRunResult:
        self.started_threads.append(agent_thread_id)
        return ExecutionRunResult(
            agent_thread_id=agent_thread_id,
            status="completed",
        )

    async def accept_resume(
        self,
        agent_thread_id: str,
        request: ExecutionResumeRequest,
    ) -> ExecutionResumeAccepted:
        if self.resume_error is not None:
            raise self.resume_error
        self.resume_requests.append((agent_thread_id, request))
        return ExecutionResumeAccepted(
            agent_thread_id=agent_thread_id,
            request_id=request.request_id,
            replayed=self.replay_resume,
        )

    async def run_accepted_resume(
        self,
        agent_thread_id: str,
        request_id: str,
    ) -> ExecutionRunResult:
        self.resumed_requests.append((agent_thread_id, request_id))
        return ExecutionRunResult(
            agent_thread_id=agent_thread_id,
            status="completed",
        )


@pytest.fixture()
def internal_api(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, StubExecutionRuntime]:
    monkeypatch.setenv("BACKEND_SERVICE_TOKEN", "backend-service-token")
    app = FastAPI()
    app.include_router(router)
    runtime = StubExecutionRuntime()
    app.state.execution_runtime = cast(ExecutionRuntime, runtime)
    return TestClient(app), runtime


def _headers(token: str = "backend-service-token") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _start_body() -> dict[str, str]:
    return {
        "request_id": "req_start_123",
        "chat_session_id": "chat_123",
        "execution_context_id": "exec_123",
        "message": "잔액을 보여줘",
    }


def _resume_body() -> dict[str, object]:
    return {
        "request_id": "req_resume_123",
        "chat_session_id": "chat_123",
        "execution_context_id": "exec_123",
        "resume": {
            "type": "input",
            "input_request_id": "input_123",
            "value": {
                "account_selection_outcome": "selected",
                "account_ids": ["acc_001"],
            },
        },
    }


def test_start_execution_accepts_and_runs_in_background(
    internal_api: tuple[TestClient, StubExecutionRuntime],
) -> None:
    client, runtime = internal_api

    response = client.post(
        "/internal/v1/executions",
        headers=_headers(),
        json=_start_body(),
    )

    assert response.status_code == 202
    assert response.json() == {"accepted": True, "agent_thread_id": "thread_123"}
    assert runtime.start_requests[0].execution_context_id == "exec_123"
    assert runtime.started_threads == ["thread_123"]


def test_duplicate_start_is_not_scheduled_twice(
    internal_api: tuple[TestClient, StubExecutionRuntime],
) -> None:
    client, runtime = internal_api
    runtime.replay_start = True

    response = client.post(
        "/internal/v1/executions",
        headers=_headers(),
        json=_start_body(),
    )

    assert response.status_code == 202
    assert runtime.started_threads == []


def test_resume_validates_then_runs_in_background(
    internal_api: tuple[TestClient, StubExecutionRuntime],
) -> None:
    client, runtime = internal_api

    response = client.post(
        "/internal/v1/executions/thread_123/resume",
        headers=_headers(),
        json=_resume_body(),
    )

    assert response.status_code == 202
    assert response.json() == {"accepted": True, "agent_thread_id": "thread_123"}
    assert runtime.resume_requests[0][0] == "thread_123"
    assert runtime.resumed_requests == [("thread_123", "req_resume_123")]


def test_internal_api_requires_backend_service_token(
    internal_api: tuple[TestClient, StubExecutionRuntime],
) -> None:
    client, _ = internal_api

    response = client.post("/internal/v1/executions", json=_start_body())

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["detail"]["code"] == "BACKEND_SERVICE_UNAUTHORIZED"


def test_resume_runtime_error_is_mapped_to_http_status(
    internal_api: tuple[TestClient, StubExecutionRuntime],
) -> None:
    client, runtime = internal_api
    runtime.resume_error = ExecutionRuntimeError(
        code="EXECUTION_NOT_FOUND",
        reason="실행을 찾을 수 없습니다.",
    )

    response = client.post(
        "/internal/v1/executions/missing/resume",
        headers=_headers(),
        json=_resume_body(),
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "EXECUTION_NOT_FOUND"
