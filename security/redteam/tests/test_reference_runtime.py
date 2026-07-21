"""Contract tests for reference workflow testbed evidence extraction."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pytest

from security.redteam.models import BusinessWorkflow
from security.redteam.runner.reference_runtime import (
    MAX_REFERENCE_TIMELINE_ITEMS,
    MAX_REFERENCE_WEBHOOK_EVENTS,
    _tool_arguments_valid,
    execute_reference_input_resume,
    execute_reference_resume,
    execute_reference_start,
)


@dataclass
class _RunResult:
    agent_thread_id: str = "thread_123"
    status: str = "completed"
    pending_interaction: dict[str, Any] | None = None


class _Testbed:
    def __init__(
        self,
        *,
        state: dict[str, Any],
        result: _RunResult | None = None,
    ) -> None:
        self._state = state
        self._result = result or _RunResult()
        self.start_arguments: dict[str, Any] | None = None
        self.resume_arguments: dict[str, Any] | None = None
        self.generic_resume_arguments: tuple[str, object] | None = None
        self._redteam_backend: Any | None = None

    async def start(
        self,
        *,
        message: str,
        request_id: str,
        chat_session_id: str,
        execution_context_id: str,
        initial_state: Mapping[str, Any] | None = None,
    ) -> _RunResult:
        self.start_arguments = {
            "message": message,
            "request_id": request_id,
            "chat_session_id": chat_session_id,
            "execution_context_id": execution_context_id,
        }
        if initial_state is not None:
            self.start_arguments["initial_state"] = initial_state
        return self._result

    async def resume_input(
        self,
        *,
        agent_thread_id: str,
        request_id: str,
        chat_session_id: str,
        execution_context_id: str,
        input_request_id: str,
        value: Mapping[str, Any],
    ) -> _RunResult:
        self.resume_arguments = {
            "agent_thread_id": agent_thread_id,
            "request_id": request_id,
            "chat_session_id": chat_session_id,
            "execution_context_id": execution_context_id,
            "input_request_id": input_request_id,
            "value": value,
        }
        return self._result

    async def resume(self, agent_thread_id: str, request: object) -> _RunResult:
        self.generic_resume_arguments = (agent_thread_id, request)
        return self._result

    async def state(self, agent_thread_id: str) -> dict[str, Any]:
        assert agent_thread_id == self._result.agent_thread_id
        return self._state

    def request_timeline(
        self,
        *,
        include_payload: bool = False,
    ) -> list[dict[str, Any]]:
        del include_payload
        return [
            {"method": "GET", "path": "/api/v1/agent-tools/accounts"},
            {
                "method": "POST",
                "path": "/api/v1/webhooks/agent",
                "step_id": "emit_balance_result",
            },
        ]

    def webhook_events(
        self,
        *,
        include_payload: bool = False,
    ) -> list[dict[str, Any]]:
        event: dict[str, Any] = {
            "event_type": "component",
            "step_id": "emit_balance_result",
        }
        if include_payload:
            event["payload"] = {
                "metadata": {"ui": {"type": "balance_result", "accounts": []}}
            }
        return [event]


class _RepeatedTimelineTestbed(_Testbed):
    def request_timeline(
        self,
        *,
        include_payload: bool = False,
    ) -> list[dict[str, Any]]:
        del include_payload
        return [
            {"method": "GET", "path": "/api/v1/agent-tools/accounts"},
            {"method": "GET", "path": "/api/v1/agent-tools/accounts"},
        ]

    def webhook_events(
        self,
        *,
        include_payload: bool = False,
    ) -> list[dict[str, Any]]:
        del include_payload
        return []


class _OversizedTimelineTestbed(_Testbed):
    def request_timeline(
        self,
        *,
        include_payload: bool = False,
    ) -> list[dict[str, Any]]:
        del include_payload
        return [
            {"method": "GET", "path": "/api/v1/agent-tools/accounts"}
            for _ in range(MAX_REFERENCE_TIMELINE_ITEMS + 1)
        ]


class _OversizedWebhookTestbed(_Testbed):
    def webhook_events(
        self,
        *,
        include_payload: bool = False,
    ) -> list[dict[str, Any]]:
        del include_payload
        return [
            {"event_type": "component", "step_id": "emit_balance_result"}
            for _ in range(MAX_REFERENCE_WEBHOOK_EVENTS + 1)
        ]


class _SensitiveWebhookTestbed(_Testbed):
    def webhook_events(
        self,
        *,
        include_payload: bool = False,
    ) -> list[dict[str, Any]]:
        event: dict[str, Any] = {
            "event_type": "component",
            "step_id": "emit_balance_result",
        }
        if include_payload:
            event["payload"] = {
                "token": "probe-secret-value",
                "metadata": {"ui": {"type": "balance_result"}},
            }
        return [event]


class _InvalidToolArgumentsTestbed(_Testbed):
    def request_timeline(
        self,
        *,
        include_payload: bool = False,
    ) -> list[dict[str, Any]]:
        item: dict[str, Any] = {
            "method": "POST",
            "path": "/api/v1/agent-tools/transactions:query",
        }
        if include_payload:
            item["payload"] = {
                "account_id": "acc_foreign",
                "from_date": "1900-01-01",
                "page_size": 999999,
            }
        return [item]


class _Backend:
    def exchange_timeline(self, *, include_payload: bool = False):
        assert include_payload is True
        return [
            {
                "method": "GET",
                "path": "/api/v1/agent-tools/accounts",
                "status_code": 200,
                "request": {},
                "response": {"account_ids": ["acc_living"]},
            }
        ]


@pytest.mark.asyncio
async def test_reference_start_preserves_state_backed_evidence() -> None:
    testbed = _Testbed(
        state={
            "workflow_id": "wf_balance_inquiry",
            "status": "completed",
            "final_response": "조회가 완료되었습니다.",
            "prompt_for": None,
            "execution_trace": [
                {"step": "resolve_accounts", "route_key": "resolved"},
                {"step": "emit_balance_result", "route_key": "completed"},
            ],
        }
    )

    response = await execute_reference_start(
        testbed,
        message="잔액을 보여줘",
        request_id="req_123",
        chat_session_id="chat_123",
        execution_context_id="exec_123",
        workflow_contract={
            "steps": [
                {
                    "step_id": "resolve_accounts",
                    "tool_id": "fetch_accounts",
                    "interaction_mode": "backend_tool_api",
                    "external_action": "GET /api/v1/agent-tools/accounts",
                },
                {
                    "step_id": "emit_balance_result",
                    "tool_id": "emit_balance_result",
                    "interaction_mode": "webhook",
                    "external_action": "component · balance_result",
                },
            ]
        },
    )

    assert testbed.start_arguments == {
        "message": "잔액을 보여줘",
        "request_id": "req_123",
        "chat_session_id": "chat_123",
        "execution_context_id": "exec_123",
    }
    assert response.status == "completed"
    assert response.ui is not None
    assert response.ui.type == "balance_result"
    assert response.execution_evidence is not None
    assert response.execution_evidence.observed_workflow_id == (
        BusinessWorkflow.BALANCE_INQUIRY
    )
    assert response.execution_evidence.tool_request_paths == [
        "/api/v1/agent-tools/accounts"
    ]
    assert response.execution_evidence.tool_requests[0].model_dump() == {
        "method": "GET",
        "path": "/api/v1/agent-tools/accounts",
        "query_keys": [],
        "payload_digest": None,
    }
    assert response.execution_evidence.contract_tool_ids == [
        "fetch_accounts",
        "emit_balance_result",
    ]
    assert response.execution_evidence.webhooks[0].step_id == "emit_balance_result"
    assert [entry.step_id for entry in response.execution_evidence.trace] == [
        "resolve_accounts",
        "emit_balance_result",
    ]


@pytest.mark.asyncio
async def test_reference_evidence_preserves_repeated_tool_calls() -> None:
    testbed = _RepeatedTimelineTestbed(
        state={
            "workflow_id": "wf_balance_inquiry",
            "status": "completed",
            "final_response": "완료",
            "execution_trace": [],
        }
    )

    response = await execute_reference_start(
        testbed,
        message="잔액을 보여줘",
        request_id="req_123",
        chat_session_id="chat_123",
        execution_context_id="exec_123",
        workflow_contract={
            "steps": [
                {
                    "step_id": "resolve_accounts",
                    "tool_id": "fetch_accounts",
                    "external_action": "GET /api/v1/agent-tools/accounts",
                }
            ]
        },
    )

    assert response.execution_evidence is not None
    assert response.execution_evidence.contract_tool_ids == [
        "fetch_accounts",
        "fetch_accounts",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("testbed_type", "message"),
    [
        (_OversizedTimelineTestbed, "reference timeline exceeds 100 entries"),
        (_OversizedWebhookTestbed, "reference webhook events exceeds 100 entries"),
    ],
)
async def test_reference_runtime_rejects_oversized_raw_evidence(
    testbed_type: type[_Testbed],
    message: str,
) -> None:
    testbed = testbed_type(
        state={
            "workflow_id": "wf_balance_inquiry",
            "status": "completed",
            "final_response": "완료",
            "execution_trace": [],
        }
    )

    with pytest.raises(ValueError, match=message):
        await execute_reference_start(
            testbed,
            message="잔액을 보여줘",
            request_id="req_123",
            chat_session_id="chat_123",
            execution_context_id="exec_123",
        )


@pytest.mark.asyncio
async def test_reference_runtime_scans_full_state_and_webhook_payloads() -> None:
    testbed = _SensitiveWebhookTestbed(
        state={
            "workflow_id": "wf_balance_inquiry",
            "status": "completed",
            "final_response": "완료",
            "token": "probe-secret-value",
            "execution_trace": [],
        }
    )

    response = await execute_reference_start(
        testbed,
        message="잔액을 보여줘",
        request_id="req_123",
        chat_session_id="chat_123",
        execution_context_id="exec_123",
    )

    assert response.execution_evidence is not None
    assert response.execution_evidence.state_contains_sensitive_data is True
    assert response.execution_evidence.webhook_payloads_contain_sensitive_data is True
    assert response.execution_evidence.state_projection_digest is not None
    assert response.execution_evidence.webhook_payload_digest is not None


@pytest.mark.asyncio
async def test_reference_runtime_rejects_invalid_tool_argument_projection() -> None:
    testbed = _InvalidToolArgumentsTestbed(
        state={
            "workflow_id": "wf_transaction_history",
            "status": "completed",
            "final_response": "완료",
            "execution_trace": [],
        }
    )
    testbed._redteam_backend = _Backend()

    response = await execute_reference_start(
        testbed,
        message="거래내역을 보여줘",
        request_id="req_123",
        chat_session_id="chat_123",
        execution_context_id="exec_123",
    )

    assert response.execution_evidence is not None
    assert response.execution_evidence.tool_arguments_valid is False
    assert response.execution_evidence.backend_exchanges_valid is True
    assert response.execution_evidence.tool_requests[0].payload_digest is not None


def test_tool_validation_does_not_trust_later_response_scope() -> None:
    exchanges = [
        {
            "method": "GET",
            "path": "/api/v1/agent-tools/accounts",
            "status_code": 200,
            "request": {},
            "response": {"account_ids": ["acc_living"]},
        },
        {
            "method": "POST",
            "path": "/api/v1/agent-tools/transactions:query",
            "status_code": 200,
            "request": {
                "account_ids": ["acc_foreign"],
                "start_date": 20260101,
                "end_date": "2026-12-31",
                "summary_type": "unsupported",
            },
            "response": {"account_id": "acc_foreign"},
        },
    ]

    assert (
        _tool_arguments_valid(
            [],
            exchanges,
            {"data": {"account_ids": ["acc_living"]}},
        )
        is False
    )


@pytest.mark.asyncio
async def test_reference_start_preserves_pending_identifiers() -> None:
    testbed = _Testbed(
        result=_RunResult(
            status="waiting",
            pending_interaction={
                "type": "input",
                "input_request_id": "input_123",
                "confirmation_id": None,
                "workflow_id": "wf_balance_inquiry",
            },
        ),
        state={
            "workflow_id": "wf_balance_inquiry",
            "status": "running",
            "final_response": None,
            "prompt_for": "balance.account_selection_input",
            "execution_trace": [],
        },
    )

    response = await execute_reference_start(
        testbed,
        message="잔액을 보여줘",
        request_id="req_123",
        chat_session_id="chat_123",
        execution_context_id="exec_123",
    )

    assert response.status == "waiting_input"
    assert response.execution_evidence is not None
    assert response.execution_evidence.pending_identifiers == {
        "input_request_id": "input_123",
        "workflow_id": "wf_balance_inquiry",
    }


@pytest.mark.asyncio
async def test_reference_input_resume_preserves_binding_and_evidence() -> None:
    testbed = _Testbed(
        result=_RunResult(status="completed"),
        state={
            "workflow_id": "wf_balance_inquiry",
            "status": "completed",
            "final_response": "조회가 완료되었습니다.",
            "execution_trace": [],
        },
    )

    response = await execute_reference_input_resume(
        testbed,
        agent_thread_id="thread_123",
        request_id="req_resume_123",
        chat_session_id="chat_123",
        execution_context_id="exec_123",
        input_request_id="input_123",
        value={
            "account_selection_outcome": "selected",
            "account_ids": ["acc_002"],
        },
    )

    assert response.status == "completed"
    assert response.thread_id == "thread_123"
    assert testbed.resume_arguments == {
        "agent_thread_id": "thread_123",
        "request_id": "req_resume_123",
        "chat_session_id": "chat_123",
        "execution_context_id": "exec_123",
        "input_request_id": "input_123",
        "value": {
            "account_selection_outcome": "selected",
            "account_ids": ["acc_002"],
        },
    }


@pytest.mark.asyncio
async def test_reference_input_resume_rejects_thread_drift() -> None:
    testbed = _Testbed(
        result=_RunResult(agent_thread_id="thread_other", status="completed"),
        state={
            "workflow_id": "wf_balance_inquiry",
            "status": "completed",
            "final_response": "조회가 완료되었습니다.",
            "execution_trace": [],
        },
    )

    with pytest.raises(ValueError, match="changed agent thread"):
        await execute_reference_input_resume(
            testbed,
            agent_thread_id="thread_123",
            request_id="req_resume_123",
            chat_session_id="chat_123",
            execution_context_id="exec_123",
            input_request_id="input_123",
            value={"account_selection_outcome": "cancelled"},
        )


@pytest.mark.asyncio
async def test_reference_generic_resume_uses_validated_request_object() -> None:
    testbed = _Testbed(
        state={
            "workflow_id": "wf_balance_inquiry",
            "status": "completed",
            "final_response": "완료",
            "execution_trace": [],
        }
    )
    request = object()

    response = await execute_reference_resume(
        testbed,
        agent_thread_id="thread_123",
        resume_request=request,
    )

    assert response.status == "completed"
    assert testbed.generic_resume_arguments == ("thread_123", request)


@pytest.mark.asyncio
async def test_global_block_without_business_id_is_global_entry() -> None:
    testbed = _Testbed(
        state={
            "status": "blocked",
            "final_response": "요청을 처리할 수 없습니다.",
            "execution_trace": [],
        }
    )

    response = await execute_reference_start(
        testbed,
        message="처리할 수 없는 요청",
        request_id="req_123",
        chat_session_id="chat_123",
        execution_context_id="exec_123",
    )

    assert response.status == "blocked"
    assert response.execution_evidence is not None
    assert response.execution_evidence.observed_workflow_id == (
        BusinessWorkflow.GLOBAL_AGENT_ENTRY
    )


@pytest.mark.asyncio
async def test_business_run_without_workflow_id_is_rejected() -> None:
    testbed = _Testbed(
        state={
            "status": "completed",
            "final_response": "완료",
            "execution_trace": [],
        }
    )

    with pytest.raises(ValueError):
        await execute_reference_start(
            testbed,
            message="잔액을 보여줘",
            request_id="req_123",
            chat_session_id="chat_123",
            execution_context_id="exec_123",
        )
