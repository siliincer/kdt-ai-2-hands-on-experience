"""기본 출금 계좌·계좌 별칭 Backend Agent Tool 계약 테스트."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from agent.clients.backend import (
    AgentToolProtocolError,
    BackendAgentTools,
    BackendClientConfig,
    BackendMutationRequestContext,
    BackendToolClient,
)
from agent.contracts.agent_tools import (
    AccountAliasPrepareRequest,
    ConfirmationExecuteRequest,
    DefaultAccountPrepareRequest,
)
from agent.tools.backend_agent_tools import (
    register_backend_agent_tools,
    register_read_backend_agent_tools,
    register_setting_backend_agent_tools,
)
from agent.tools.contract_registry import (
    ContractToolCall,
    ContractToolInputError,
    ContractToolRegistry,
)
from agent.workflow_contracts import WorkflowContractStore


def _config() -> BackendClientConfig:
    return BackendClientConfig(
        base_url="http://backend.test",
        agent_service_token=SecretStr("service-token"),
        agent_webhook_secret=SecretStr("webhook-secret"),
        retry_backoff_seconds=0,
    )


def _context(key: str) -> BackendMutationRequestContext:
    return BackendMutationRequestContext(
        execution_context_id="exec_123",
        request_id="req_123",
        idempotency_key=key,
    )


def _success(data: dict[str, object]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"success": True, "message": "처리 완료", "data": data},
    )


def _account(account_id: str, alias: str | None = None) -> dict[str, object]:
    return {
        "account_id": account_id,
        "bank_name": "신한은행",
        "account_alias": alias,
        "masked_account_number": "110-***-123456",
    }


@pytest.mark.asyncio
async def test_default_account_prepare_and_execute_use_confirmation_contract() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.url.path.endswith(":prepare"):
            return _success(
                {
                    "outcome": "ready_for_confirmation",
                    "confirmation_id": "confirm_default_123",
                    "confirmation_view": {
                        "current_default_account": _account("acc_001", "생활비"),
                        "new_default_account": _account("acc_002", "급여"),
                        "expires_at": "2026-07-16T10:05:00+09:00",
                    },
                }
            )
        return _success(
            {
                "outcome": "completed",
                "account_id": "acc_002",
                "completed_at": "2026-07-16T10:04:00+09:00",
            }
        )

    async with httpx.AsyncClient(
        base_url="http://backend.test",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        tools = BackendAgentTools(BackendToolClient(_config(), client=http_client))
        prepare_result = await tools.prepare_default_account_change(
            DefaultAccountPrepareRequest(account_id="acc_002"),
            context=_context("default_account_prepare:exec_123:1"),
        )
        execute_result = await tools.execute_default_account_change(
            ConfirmationExecuteRequest(confirmation_id="confirm_default_123"),
            context=_context("default_account_execute:confirm_default_123"),
        )

    assert [request.url.path for request in captured] == [
        "/api/v1/agent-tools/settings/default-account:prepare",
        "/api/v1/agent-tools/settings/default-account",
    ]
    assert json.loads(captured[0].content) == {"account_id": "acc_002", "unset": False}
    assert json.loads(captured[1].content) == {"confirmation_id": "confirm_default_123"}
    assert captured[1].headers["idempotency-key"] == ("default_account_execute:confirm_default_123")
    assert prepare_result.confirmation_view is not None
    assert prepare_result.confirmation_view.new_default_account.account_id == "acc_002"
    assert execute_result.account_id == "acc_002"


@pytest.mark.asyncio
async def test_account_alias_prepare_contains_only_target_and_alias() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _success(
            {
                "outcome": "ready_for_confirmation",
                "confirmation_id": "confirm_alias_123",
                "confirmation_view": {
                    "account": {
                        "account_id": "acc_001",
                        "bank_name": "신한은행",
                        "masked_account_number": "110-***-123456",
                    },
                    "alias": "여행 자금",
                    "expires_at": "2026-07-16T10:05:00+09:00",
                },
            }
        )

    async with httpx.AsyncClient(
        base_url="http://backend.test",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        tools = BackendAgentTools(BackendToolClient(_config(), client=http_client))
        result = await tools.prepare_account_alias_change(
            AccountAliasPrepareRequest(account_id="acc_001", alias="여행 자금"),
            context=_context("account_alias_prepare:exec_123:1"),
        )

    assert captured[0].url.path == ("/api/v1/agent-tools/settings/account-alias:prepare")
    assert json.loads(captured[0].content) == {
        "account_id": "acc_001",
        "alias": "여행 자금",
    }
    assert result.confirmation_view is not None
    assert result.confirmation_view.alias == "여행 자금"


@pytest.mark.asyncio
async def test_account_alias_execute_supports_single_correction_target() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return _success(
            {
                "outcome": "correction_required",
                "reason": "alias_not_allowed",
                "correction_view": {"allowed_change_targets": ["alias"]},
            }
        )

    async with httpx.AsyncClient(
        base_url="http://backend.test",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        tools = BackendAgentTools(BackendToolClient(_config(), client=http_client))
        result = await tools.execute_account_alias_change(
            ConfirmationExecuteRequest(confirmation_id="confirm_alias_123"),
            context=_context("account_alias_execute:confirm_alias_123"),
        )

    assert result.correction_view is not None
    assert result.correction_view.allowed_change_targets == ["alias"]


@pytest.mark.asyncio
async def test_alias_contract_rejects_account_label_and_current_alias() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return _success(
            {
                "outcome": "ready_for_confirmation",
                "confirmation_id": "confirm_alias_123",
                "confirmation_view": {
                    "account": {
                        "account_id": "acc_001",
                        "bank_name": "신한은행",
                        "masked_account_number": "110-***-123456",
                        "account_label": "생활비 통장",
                    },
                    "current_alias": "생활비",
                    "alias": "여행 자금",
                    "expires_at": "2026-07-16T10:05:00+09:00",
                },
            }
        )

    async with httpx.AsyncClient(
        base_url="http://backend.test",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        tools = BackendAgentTools(BackendToolClient(_config(), client=http_client))
        with pytest.raises(AgentToolProtocolError):
            await tools.prepare_account_alias_change(
                AccountAliasPrepareRequest(account_id="acc_001", alias="여행 자금"),
                context=_context("account_alias_prepare:exec_123:1"),
            )


def test_setting_request_and_response_contracts_reject_invalid_shapes() -> None:
    with pytest.raises(ValidationError):
        AccountAliasPrepareRequest(account_id="acc_001", alias="")


@pytest.mark.asyncio
async def test_setting_registry_requires_idempotency_and_completes_workflows() -> None:
    async with httpx.AsyncClient(
        base_url="http://backend.test",
        transport=httpx.MockTransport(lambda _: _success({"outcome": "unchanged", "account_id": "acc_002"})),
    ) as http_client:
        tools = BackendAgentTools(BackendToolClient(_config(), client=http_client))
        registry = ContractToolRegistry(WorkflowContractStore())
        register_read_backend_agent_tools(registry, tools)
        register_setting_backend_agent_tools(registry, tools)

        with pytest.raises(ContractToolInputError) as raised:
            await registry.invoke_by_tool(
                "prepare_default_account_change",
                ContractToolCall(
                    execution_context_id="exec_123",
                    request_id="req_123",
                    arguments={"account_id": "acc_002"},
                ),
            )

    assert raised.value.contract_id == "API-DEFAULT-ACCOUNT-PREPARE"
    assert registry.missing_contracts_for_workflow("wf_set_default_account") == set()
    assert registry.missing_contracts_for_workflow("wf_set_account_alias") == set()


@pytest.mark.asyncio
async def test_common_registration_covers_all_workflow_api_contracts() -> None:
    contract_store = WorkflowContractStore()
    registry = ContractToolRegistry(contract_store)

    async with httpx.AsyncClient(base_url="http://backend.test") as http_client:
        tools = BackendAgentTools(BackendToolClient(_config(), client=http_client))
        register_backend_agent_tools(registry, tools)

    for workflow_id in contract_store.workflow_ids():
        assert registry.missing_contracts_for_workflow(workflow_id) == set()
