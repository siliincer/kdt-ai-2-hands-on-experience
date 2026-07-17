"""송금·추가 인증 Backend Agent Tool 계약 테스트."""

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
    AuthContextCreateRequest,
    ExternalTransferPrepareRequest,
    InternalTransferPrepareRequest,
    TransferExecuteRequest,
)
from agent.tools.backend_agent_tools import (
    register_read_backend_agent_tools,
    register_transfer_backend_agent_tools,
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


def _context(
    key: str = "external_transfer_prepare:exec_123:1",
) -> BackendMutationRequestContext:
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


def _account(account_id: str, alias: str) -> dict[str, object]:
    return {
        "account_id": account_id,
        "bank_name": "신한은행",
        "account_alias": alias,
        "masked_account_number": "110-***-123456",
    }


def _external_confirmation_view() -> dict[str, object]:
    return {
        "from_account": _account("acc_001", "생활비"),
        "recipient": {
            "name": "홍*동",
            "bank_name": "국민은행",
            "masked_account_number": "110-***-654321",
        },
        "amount": 50000,
        "fee": 0,
        "total_debit": 50000,
        "currency": "KRW",
        "variant": "warning",
        "warning_codes": ["NEW_RECIPIENT"],
        "expires_at": "2026-07-16T10:05:00+09:00",
    }


def _internal_confirmation_view() -> dict[str, object]:
    return {
        "from_account": _account("acc_001", "생활비"),
        "to_account": _account("acc_002", "저축"),
        "amount": 100000,
        "fee": 0,
        "total_debit": 100000,
        "currency": "KRW",
        "expires_at": "2026-07-16T10:05:00+09:00",
    }


@pytest.mark.asyncio
async def test_prepare_external_transfer_sends_exact_contract() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _success(
            {
                "outcome": "ready_for_confirmation",
                "confirmation_id": "confirm_123",
                "confirmation_view": _external_confirmation_view(),
            }
        )

    async with httpx.AsyncClient(
        base_url="http://backend.test",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        tools = BackendAgentTools(BackendToolClient(_config(), client=http_client))
        result = await tools.prepare_external_transfer(
            ExternalTransferPrepareRequest(
                from_account_id="acc_001",
                to_recipient_id="rcp_001",
                amount=50000,
            ),
            context=_context(),
        )

    request = captured[0]
    assert request.url.path == "/api/v1/agent-tools/transfers/external:prepare"
    assert request.headers["idempotency-key"] == "external_transfer_prepare:exec_123:1"
    assert json.loads(request.content) == {
        "from_account_id": "acc_001",
        "to_recipient_id": "rcp_001",
        "amount": 50000,
        "currency": "KRW",
    }
    assert result.confirmation_id == "confirm_123"
    assert result.confirmation_view is not None
    assert result.confirmation_view.recipient.name == "홍*동"


@pytest.mark.asyncio
async def test_create_auth_context_and_execute_external_transfer() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.url.path.endswith("/auth-contexts"):
            return _success(
                {
                    "outcome": "authentication_required",
                    "auth_context_id": "auth_123",
                    "auth_request_view": {
                        "title": "추가 인증이 필요합니다.",
                        "description": "인증을 완료해 주세요.",
                        "available_methods": ["biometric", "password"],
                        "expires_at": "2026-07-16T10:08:00+09:00",
                    },
                }
            )
        return _success(
            {
                "outcome": "completed",
                "transaction_id": "txn_123",
                "completed_at": "2026-07-16T10:04:00+09:00",
            }
        )

    async with httpx.AsyncClient(
        base_url="http://backend.test",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        tools = BackendAgentTools(BackendToolClient(_config(), client=http_client))
        auth_result = await tools.create_auth_context(
            AuthContextCreateRequest(confirmation_id="confirm_123"),
            context=_context("external_transfer_auth:confirm_123:1"),
        )
        execute_result = await tools.execute_external_transfer(
            TransferExecuteRequest(
                confirmation_id="confirm_123",
                auth_context_id="auth_123",
            ),
            context=_context("external_transfer_execute:confirm_123:1"),
        )

    assert [request.url.path for request in captured] == [
        "/api/v1/agent-tools/auth-contexts",
        "/api/v1/agent-tools/transfers/external",
    ]
    assert captured[1].headers["idempotency-key"] == (
        "external_transfer_execute:confirm_123:1"
    )
    assert auth_result.auth_context_id == "auth_123"
    assert execute_result.transaction_id == "txn_123"


@pytest.mark.asyncio
async def test_internal_transfer_supports_correction_and_reauthentication() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.url.path.endswith(":prepare"):
            return _success(
                {
                    "outcome": "correction_required",
                    "reason": "insufficient_balance",
                    "correction_view": {
                        "allowed_change_targets": ["from_account", "amount"]
                    },
                }
            )
        return _success(
            {
                "outcome": "reauthentication_required",
                "reason": "auth_context_expired",
            }
        )

    async with httpx.AsyncClient(
        base_url="http://backend.test",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        tools = BackendAgentTools(BackendToolClient(_config(), client=http_client))
        prepare_result = await tools.prepare_internal_transfer(
            InternalTransferPrepareRequest(
                from_account_id="acc_001",
                to_account_id="acc_002",
                amount=100000,
            ),
            context=_context("internal_transfer_prepare:exec_123:1"),
        )
        execute_result = await tools.execute_internal_transfer(
            TransferExecuteRequest(
                confirmation_id="confirm_internal_123",
                auth_context_id="auth_internal_123",
            ),
            context=_context("internal_transfer_execute:confirm_internal_123:1"),
        )

    assert [request.url.path for request in captured] == [
        "/api/v1/agent-tools/transfers/internal:prepare",
        "/api/v1/agent-tools/transfers/internal",
    ]
    assert prepare_result.correction_view is not None
    assert prepare_result.correction_view.allowed_change_targets == [
        "from_account",
        "amount",
    ]
    assert execute_result.outcome == "reauthentication_required"


def test_transfer_requests_reject_ambiguous_or_invalid_accounts() -> None:
    with pytest.raises(ValidationError):
        ExternalTransferPrepareRequest(
            from_account_id="acc_001",
            amount=50000,
        )
    with pytest.raises(ValidationError):
        ExternalTransferPrepareRequest(
            from_account_id="acc_001",
            to_recipient_id="rcp_001",
            to_recipient_candidate_id="candidate_001",
            amount=50000,
        )
    with pytest.raises(ValidationError):
        InternalTransferPrepareRequest(
            from_account_id="acc_001",
            to_account_id="acc_001",
            amount=100000,
        )


@pytest.mark.asyncio
async def test_transfer_registry_requires_idempotency_and_completes_workflows() -> None:
    async with httpx.AsyncClient(
        base_url="http://backend.test",
        transport=httpx.MockTransport(
            lambda _: _success(
                {
                    "outcome": "ready_for_confirmation",
                    "confirmation_id": "confirm_123",
                    "confirmation_view": _internal_confirmation_view(),
                }
            )
        ),
    ) as http_client:
        tools = BackendAgentTools(BackendToolClient(_config(), client=http_client))
        registry = ContractToolRegistry(WorkflowContractStore())
        register_read_backend_agent_tools(registry, tools)
        register_transfer_backend_agent_tools(registry, tools)

        with pytest.raises(ContractToolInputError) as raised:
            await registry.invoke_by_tool(
                "prepare_internal_transfer",
                ContractToolCall(
                    execution_context_id="exec_123",
                    request_id="req_123",
                    arguments={
                        "from_account_id": "acc_001",
                        "to_account_id": "acc_002",
                        "amount": 100000,
                        "currency": "KRW",
                    },
                ),
            )

    assert raised.value.contract_id == "API-INTERNAL-TRANSFER-PREPARE"
    assert registry.missing_contracts_for_workflow("wf_external_transfer") == set()
    assert registry.missing_contracts_for_workflow("wf_internal_transfer") == set()


@pytest.mark.asyncio
async def test_transfer_adapter_rejects_mixed_outcome_fields() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return _success(
            {
                "outcome": "completed",
                "transaction_id": "txn_123",
                "completed_at": "2026-07-16T10:04:00+09:00",
                "reason": "must_not_exist",
            }
        )

    async with httpx.AsyncClient(
        base_url="http://backend.test",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        tools = BackendAgentTools(BackendToolClient(_config(), client=http_client))
        with pytest.raises(AgentToolProtocolError):
            await tools.execute_external_transfer(
                TransferExecuteRequest(
                    confirmation_id="confirm_123",
                    auth_context_id="auth_123",
                ),
                context=_context("external_transfer_execute:confirm_123:1"),
            )
