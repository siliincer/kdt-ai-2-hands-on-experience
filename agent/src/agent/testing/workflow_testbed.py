"""Notebook과 pytest가 함께 사용하는 Workflow 실행 Harness."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, TypeVar

import httpx
from langgraph.checkpoint.memory import MemorySaver

from agent.clients.backend import (
    BackendAgentTools,
    BackendClientConfig,
    BackendToolClient,
    BackendWebhookClient,
)
from agent.runtime import (
    ExecutionGraph,
    ExecutionResumeRequest,
    ExecutionRunResult,
    ExecutionRuntime,
    ExecutionStartRequest,
    InteractionPauseRuntime,
    InteractionWebhookBuilder,
    ResumeStateMapper,
)
from agent.tools.backend_agent_tools import register_backend_agent_tools
from agent.tools.contract_registry import ContractToolRegistry
from agent.workflow_contracts import WorkflowContractStore


@dataclass(frozen=True, slots=True)
class WorkflowTestbedDependencies:
    """Workflow별 Testbed Factory에 전달하는 공통 실행 의존성."""

    tool_registry: ContractToolRegistry
    webhook_client: BackendWebhookClient
    interaction_runtime: InteractionPauseRuntime
    webhook_builder: InteractionWebhookBuilder
    checkpointer: Any


TestbedGraphFactory = Callable[[WorkflowTestbedDependencies], ExecutionGraph]
_ValueT = TypeVar("_ValueT")


def constant_factory(value: _ValueT) -> Callable[[], _ValueT]:
    """Testbed에서 동일한 식별자나 시각을 반복 반환하는 Factory를 만든다."""

    return lambda: value


def sequence_factory(values: Iterable[_ValueT]) -> Callable[[], _ValueT]:
    """Testbed 호출 순서에 따라 준비된 값을 하나씩 반환하는 Factory를 만든다."""

    iterator = iter(values)
    return lambda: next(iterator)


@dataclass(slots=True)
class WorkflowTestbed:
    """한 Workflow Scenario의 시작, Resume, State와 HTTP 이력을 제공한다."""

    runtime: ExecutionRuntime
    graph: ExecutionGraph
    http_client: httpx.AsyncClient
    requests: list[httpx.Request]

    async def start(
        self,
        *,
        message: str,
        request_id: str,
        chat_session_id: str,
        execution_context_id: str,
        initial_state: Mapping[str, Any] | None = None,
    ) -> ExecutionRunResult:
        """Backend의 실행 시작 요청과 같은 모델로 Workflow를 실행한다."""

        return await self.runtime.start(
            ExecutionStartRequest(
                request_id=request_id,
                chat_session_id=chat_session_id,
                execution_context_id=execution_context_id,
                message=message,
            ),
            initial_state=initial_state,
        )

    async def resume(
        self,
        agent_thread_id: str,
        request: ExecutionResumeRequest,
    ) -> ExecutionRunResult:
        """Backend가 검증한 Resume 요청으로 중단된 Workflow를 재개한다."""

        return await self.runtime.resume(agent_thread_id, request)

    async def resume_input(
        self,
        *,
        agent_thread_id: str,
        request_id: str,
        chat_session_id: str,
        execution_context_id: str,
        input_request_id: str,
        value: Mapping[str, Any],
    ) -> ExecutionRunResult:
        """검증 완료된 일반 사용자 입력 Resume을 간단히 구성한다."""

        request = ExecutionResumeRequest.model_validate(
            {
                "request_id": request_id,
                "chat_session_id": chat_session_id,
                "execution_context_id": execution_context_id,
                "resume": {
                    "type": "input",
                    "input_request_id": input_request_id,
                    "value": dict(value),
                },
            }
        )
        return await self.resume(agent_thread_id, request)

    async def state(self, agent_thread_id: str) -> dict[str, Any]:
        """Checkpoint에 저장된 현재 State를 복사해 반환한다."""

        snapshot = await self.graph.aget_state({"configurable": {"thread_id": agent_thread_id}})
        return dict(snapshot.values)

    def request_timeline(
        self,
        *,
        include_payload: bool = False,
    ) -> list[dict[str, Any]]:
        """인증 Header를 제외한 Tool과 Webhook 호출 순서를 반환한다."""

        return [_request_summary(request, include_payload=include_payload) for request in self.requests]

    def webhook_events(self, *, include_payload: bool = False) -> list[dict[str, Any]]:
        """Webhook 호출만 안전한 요약 또는 전체 Payload로 반환한다."""

        return [
            _request_summary(request, include_payload=include_payload)
            for request in self.requests
            if request.url.path == "/api/v1/webhooks/agent"
        ]

    async def aclose(self) -> None:
        """Harness가 소유한 HTTP Client를 종료한다."""

        await self.http_client.aclose()

    async def __aenter__(self) -> WorkflowTestbed:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()


def create_workflow_testbed(
    config: BackendClientConfig,
    *,
    graph_factory: TestbedGraphFactory,
    transport: httpx.AsyncBaseTransport | None = None,
    thread_id: str | None = None,
) -> WorkflowTestbed:
    """공통 HTTP·계약·Runtime을 조립하고 Workflow Graph만 주입받는다."""

    requests: list[httpx.Request] = []

    async def capture_request(request: httpx.Request) -> None:
        requests.append(request)

    http_client = httpx.AsyncClient(
        base_url=config.base_url.rstrip("/"),
        timeout=httpx.Timeout(
            timeout=config.request_timeout_seconds,
            connect=config.connect_timeout_seconds,
        ),
        transport=transport,
        event_hooks={"request": [capture_request]},
    )
    contract_store = WorkflowContractStore()
    tool_registry = ContractToolRegistry(contract_store)
    backend_tools = BackendAgentTools(BackendToolClient(config, client=http_client))
    register_backend_agent_tools(tool_registry, backend_tools)
    webhook_client = BackendWebhookClient(config, client=http_client)
    interaction_runtime = InteractionPauseRuntime(webhook_client)
    graph = graph_factory(
        WorkflowTestbedDependencies(
            tool_registry=tool_registry,
            webhook_client=webhook_client,
            interaction_runtime=interaction_runtime,
            webhook_builder=InteractionWebhookBuilder(contract_store),
            checkpointer=MemorySaver(),
        )
    )
    runtime = ExecutionRuntime(
        graph=graph,
        interaction_runtime=interaction_runtime,
        resume_mapper=ResumeStateMapper(contract_store),
        thread_id_factory=(lambda: thread_id) if thread_id is not None else None,
    )
    return WorkflowTestbed(
        runtime=runtime,
        graph=graph,
        http_client=http_client,
        requests=requests,
    )


def _request_summary(
    request: httpx.Request,
    *,
    include_payload: bool,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "method": request.method,
        "path": request.url.path,
        "request_id": request.headers.get("x-request-id"),
        "execution_context_id": request.headers.get("x-execution-context-id"),
    }
    if request.url.params:
        summary["query_keys"] = sorted(set(request.url.params.keys()))

    payload = _json_payload(request)
    if request.url.path == "/api/v1/webhooks/agent" and payload is not None:
        summary["event_type"] = payload.get("event_type")
        metadata = payload.get("metadata")
        if isinstance(metadata, Mapping):
            summary["step_id"] = metadata.get("step_id")
    if include_payload and payload is not None:
        summary["payload"] = payload
    return summary


def _json_payload(request: httpx.Request) -> dict[str, Any] | None:
    if not request.content:
        return None
    try:
        payload = json.loads(request.content)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return dict(payload) if isinstance(payload, Mapping) else None
