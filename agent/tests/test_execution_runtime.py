"""공통 Execution Runtime의 시작, 중단, Resume과 중복 방지 테스트."""

from __future__ import annotations

from typing import Annotated, Any, TypedDict, cast

import httpx
import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from pydantic import SecretStr

from agent.clients.backend import BackendClientConfig, BackendWebhookClient
from agent.runtime import (
    ExecutionGraph,
    ExecutionResumeRequest,
    ExecutionRuntime,
    ExecutionRuntimeError,
    ExecutionStartRequest,
    InteractionPauseRuntime,
    InteractionWebhookBuilder,
    ResumeStateMapper,
    ResumeValidationError,
)
from agent.workflow_contracts import WorkflowContractStore


def _merge_data(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    return {**left, **right}


class RuntimeState(TypedDict, total=False):
    user_input: str
    status: str
    data: Annotated[dict[str, Any], _merge_data]
    logs: list[Any]
    execution_trace: list[Any]
    observed_amount: int | None
    node_calls: int


def _start_request(*, message: str = "홍길동에게 송금해줘") -> ExecutionStartRequest:
    return ExecutionStartRequest(
        request_id="req_start_123",
        chat_session_id="chat_123",
        execution_context_id="exec_123",
        message=message,
    )


def _resume_request(
    *,
    request_id: str = "req_resume_123",
    input_request_id: str = "input_amount_123",
) -> ExecutionResumeRequest:
    return ExecutionResumeRequest.model_validate(
        {
            "request_id": request_id,
            "chat_session_id": "chat_123",
            "execution_context_id": "exec_123",
            "resume": {
                "type": "input",
                "input_request_id": input_request_id,
                "value": {
                    "amount_input_outcome": "submitted",
                    "amount": 50000,
                    "unmapped_field": "must_not_enter_state",
                },
            },
        }
    )


def _client_config() -> BackendClientConfig:
    return BackendClientConfig(
        base_url="http://backend.test",
        agent_service_token=SecretStr("service-token"),
        agent_webhook_secret=SecretStr("webhook-secret"),
        retry_backoff_seconds=0,
    )


def _webhook_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "success": True,
            "message": "이벤트 발행 완료",
            "data": {"message_id": "message_123"},
        },
    )


@pytest.mark.asyncio
async def test_start_resume_maps_state_and_publishes_interrupt_once() -> None:
    webhook_requests: list[httpx.Request] = []
    node_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        webhook_requests.append(request)
        return _webhook_response()

    async with httpx.AsyncClient(
        base_url="http://backend.test",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        webhook_client = BackendWebhookClient(_client_config(), client=http_client)
        interaction_runtime = InteractionPauseRuntime(webhook_client)
        event = InteractionWebhookBuilder(WorkflowContractStore()).need_input(
            chat_session_id="chat_123",
            workflow_id="wf_external_transfer",
            step_id="request_external_transfer_amount",
            input_request_id="input_amount_123",
            ui_contract_id="UI-TRANSFER-AMOUNT-INPUT",
            ui_type="number_input",
            content="금액을 입력해 주세요.",
            payload={"currency": "KRW", "min": 1},
        )

        def amount_node(state: RuntimeState) -> RuntimeState:
            nonlocal node_calls
            node_calls += 1
            interaction_runtime.pause(event)
            return {
                "data": {"input_request_id": None},
                "observed_amount": state.get("data", {}).get("amount"),
                "node_calls": node_calls,
            }

        builder = StateGraph(RuntimeState)
        builder.add_node("amount", amount_node)
        builder.set_entry_point("amount")
        builder.add_edge("amount", END)
        graph = builder.compile(checkpointer=MemorySaver())
        runtime = ExecutionRuntime(
            graph=cast(ExecutionGraph, graph),
            interaction_runtime=interaction_runtime,
            resume_mapper=ResumeStateMapper(WorkflowContractStore()),
            thread_id_factory=lambda: "thread_123",
        )

        interrupted = await runtime.start(_start_request())
        resume_accepted = await runtime.accept_resume(
            "thread_123",
            _resume_request(),
        )
        completed = await runtime.run_accepted_resume(
            "thread_123",
            resume_accepted.request_id,
        )
        replayed = await runtime.resume("thread_123", _resume_request())
        snapshot = await graph.aget_state(
            {"configurable": {"thread_id": "thread_123"}}
        )

    assert interrupted.status == "waiting"
    assert interrupted.pending_interaction is not None
    assert interrupted.pending_interaction["input_request_id"] == "input_amount_123"
    assert resume_accepted.replayed is False
    assert completed.status == "completed"
    assert replayed.status == "completed"
    assert replayed.replayed is True
    assert snapshot.values["observed_amount"] == 50000
    assert snapshot.values["data"] == {
        "amount_input_outcome": "submitted",
        "amount": 50000,
        "input_request_id": None,
    }
    assert node_calls == 2
    assert len(webhook_requests) == 1
    assert webhook_requests[0].headers["x-execution-context-id"] == "exec_123"


@pytest.mark.asyncio
async def test_duplicate_start_reuses_thread_without_running_graph_again() -> None:
    node_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return _webhook_response()

    async with httpx.AsyncClient(
        base_url="http://backend.test",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        interaction_runtime = InteractionPauseRuntime(
            BackendWebhookClient(_client_config(), client=http_client)
        )
        event = InteractionWebhookBuilder(WorkflowContractStore()).need_input(
            chat_session_id="chat_123",
            workflow_id="wf_external_transfer",
            step_id="request_external_transfer_amount",
            input_request_id="input_amount_123",
            ui_contract_id="UI-TRANSFER-AMOUNT-INPUT",
            ui_type="number_input",
            content="금액을 입력해 주세요.",
            payload={"currency": "KRW"},
        )

        def pause_node(state: RuntimeState) -> RuntimeState:
            nonlocal node_calls
            del state
            node_calls += 1
            interaction_runtime.pause(event)
            return {"node_calls": node_calls}

        builder = StateGraph(RuntimeState)
        builder.add_node("pause", pause_node)
        builder.set_entry_point("pause")
        builder.add_edge("pause", END)
        runtime = ExecutionRuntime(
            graph=cast(
                ExecutionGraph,
                builder.compile(checkpointer=MemorySaver()),
            ),
            interaction_runtime=interaction_runtime,
            resume_mapper=ResumeStateMapper(WorkflowContractStore()),
            thread_id_factory=lambda: "thread_123",
        )

        first = await runtime.start(_start_request())
        duplicate = await runtime.start(_start_request())

    assert first.agent_thread_id == duplicate.agent_thread_id == "thread_123"
    assert duplicate.status == "waiting"
    assert duplicate.replayed is True
    assert node_calls == 1


@pytest.mark.asyncio
async def test_runtime_rejects_conflicting_start_and_stale_resume() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return _webhook_response()

    async with httpx.AsyncClient(
        base_url="http://backend.test",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        interaction_runtime = InteractionPauseRuntime(
            BackendWebhookClient(_client_config(), client=http_client)
        )
        event = InteractionWebhookBuilder(WorkflowContractStore()).need_input(
            chat_session_id="chat_123",
            workflow_id="wf_external_transfer",
            step_id="request_external_transfer_amount",
            input_request_id="input_amount_123",
            ui_contract_id="UI-TRANSFER-AMOUNT-INPUT",
            ui_type="number_input",
            content="금액을 입력해 주세요.",
            payload={"currency": "KRW"},
        )

        def pause_node(state: RuntimeState) -> RuntimeState:
            del state
            interaction_runtime.pause(event)
            return {}

        builder = StateGraph(RuntimeState)
        builder.add_node("pause", pause_node)
        builder.set_entry_point("pause")
        builder.add_edge("pause", END)
        runtime = ExecutionRuntime(
            graph=cast(
                ExecutionGraph,
                builder.compile(checkpointer=MemorySaver()),
            ),
            interaction_runtime=interaction_runtime,
            resume_mapper=ResumeStateMapper(WorkflowContractStore()),
            thread_id_factory=lambda: "thread_123",
        )
        await runtime.start(_start_request())

        with pytest.raises(ExecutionRuntimeError) as conflicting_start:
            runtime.accept_start(_start_request(message="다른 요청"))
        with pytest.raises(ResumeValidationError) as stale_resume:
            await runtime.resume(
                "thread_123",
                _resume_request(input_request_id="input_stale"),
            )

    assert conflicting_start.value.code == "START_REQUEST_ID_CONFLICT"
    assert stale_resume.value.code == "PENDING_IDENTIFIER_MISMATCH"
