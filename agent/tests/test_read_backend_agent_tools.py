"""조회 계열 Backend Agent Tool 계약 테스트."""

from __future__ import annotations

import json
from datetime import date

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from agent.clients.backend import (
    AgentToolProtocolError,
    BackendAgentTools,
    BackendClientConfig,
    BackendRequestContext,
    BackendToolClient,
)
from agent.contracts.agent_tools import (
    AccountListRequest,
    BalanceQueryRequest,
    RecipientResolveRequest,
    TransactionQueryRequest,
    TransactionSummaryRequest,
)
from agent.tools.backend_agent_tools import register_read_backend_agent_tools
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


def _context() -> BackendRequestContext:
    return BackendRequestContext(
        execution_context_id="exec_123",
        request_id="req_123",
    )


def _success(data: dict[str, object]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"success": True, "message": "조회 완료", "data": data},
    )


@pytest.mark.asyncio
async def test_fetch_accounts_uses_query_contract_and_parses_resolution() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _success(
            {
                "account_resolution_outcome": "resolved",
                "account_ids": ["acc_001"],
                "accounts": [
                    {
                        "account_id": "acc_001",
                        "bank_name": "신한은행",
                        "account_alias": "급여 계좌",
                        "account_type": "checking",
                        "masked_account_number": "110-***-123456",
                        "currency": "KRW",
                        "is_default": True,
                        "status": "active",
                    }
                ],
            }
        )

    async with httpx.AsyncClient(
        base_url="http://backend.test",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        tools = BackendAgentTools(BackendToolClient(_config(), client=http_client))
        result = await tools.fetch_accounts(
            AccountListRequest(
                account_hint="신한은행",
                account_capability="withdraw",
                resolve_selection=True,
            ),
            context=_context(),
        )

    request = captured[0]
    assert request.method == "GET"
    assert request.url.path == "/api/v1/agent-tools/accounts"
    assert request.url.params["account_hint"] == "신한은행"
    assert request.url.params["account_capability"] == "withdraw"
    assert request.url.params["resolve_selection"] == "true"
    assert result.account_ids == ["acc_001"]
    assert result.accounts[0].is_default is True


@pytest.mark.asyncio
async def test_query_balances_sends_account_ids_once() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _success(
            {
                "balance_results": [
                    {
                        "account_id": "acc_001",
                        "bank_name": "신한은행",
                        "account_alias": "급여 계좌",
                        "masked_account_number": "110-***-123456",
                        "balance": 5300000,
                        "available_balance": 5200000,
                        "currency": "KRW",
                        "as_of": "2026-07-16T10:00:00+09:00",
                    }
                ]
            }
        )

    async with httpx.AsyncClient(
        base_url="http://backend.test",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        tools = BackendAgentTools(BackendToolClient(_config(), client=http_client))
        result = await tools.query_balances(
            BalanceQueryRequest(account_ids=["acc_001"]),
            context=_context(),
        )

    assert captured[0].url.path == "/api/v1/agent-tools/accounts/balances:query"
    assert json.loads(captured[0].content) == {"account_ids": ["acc_001"]}
    assert result.balance_results[0].available_balance == 5200000


@pytest.mark.asyncio
async def test_query_transactions_preserves_first_page_contract() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _success(
            {
                "transaction_results": [],
                "transaction_query_id": "txq_123",
                "next_cursor": None,
            }
        )

    async with httpx.AsyncClient(
        base_url="http://backend.test",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        tools = BackendAgentTools(BackendToolClient(_config(), client=http_client))
        result = await tools.query_transactions(
            TransactionQueryRequest(
                account_ids=["acc_001"],
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 16),
                keyword="배민",
                transaction_type="card_payment",
            ),
            context=_context(),
        )

    body = json.loads(captured[0].content)
    assert captured[0].url.path == "/api/v1/agent-tools/transactions:query"
    assert body["keyword"] == "배민"
    assert body["limit"] == 10
    assert "cursor" not in body
    assert result.transaction_query_id == "txq_123"


@pytest.mark.asyncio
async def test_query_transaction_summary_uses_backend_aggregate() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return _success(
            {
                "summary_result": {
                    "summary_type": "spending",
                    "total_amount": 42000,
                    "transaction_count": 3,
                    "currency": "KRW",
                    "start_date": "2026-07-01",
                    "end_date": "2026-07-16",
                }
            }
        )

    async with httpx.AsyncClient(
        base_url="http://backend.test",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        tools = BackendAgentTools(BackendToolClient(_config(), client=http_client))
        result = await tools.query_transaction_summary(
            TransactionSummaryRequest(
                account_ids=["acc_001"],
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 16),
                summary_type="spending",
                keyword="배민",
            ),
            context=_context(),
        )

    assert result.summary_result.total_amount == 42000
    assert result.summary_result.transaction_count == 3


@pytest.mark.asyncio
async def test_resolve_recipient_returns_only_selection_reason() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return _success(
            {
                "outcome": "selection_required",
                "selection_reason": "multiple_matches",
            }
        )

    async with httpx.AsyncClient(
        base_url="http://backend.test",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        tools = BackendAgentTools(BackendToolClient(_config(), client=http_client))
        result = await tools.resolve_recipient(
            RecipientResolveRequest(recipient_name_hint="홍길동"),
            context=_context(),
        )

    assert result.outcome == "selection_required"
    assert result.selection_reason == "multiple_matches"
    assert result.to_recipient_id is None


@pytest.mark.asyncio
async def test_typed_adapter_rejects_backend_data_contract_mismatch() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return _success(
            {
                "outcome": "resolved",
                "selection_reason": "multiple_matches",
            }
        )

    async with httpx.AsyncClient(
        base_url="http://backend.test",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        tools = BackendAgentTools(BackendToolClient(_config(), client=http_client))
        with pytest.raises(AgentToolProtocolError):
            await tools.resolve_recipient(
                RecipientResolveRequest(recipient_name_hint="홍길동"),
                context=_context(),
            )


def test_read_request_contract_rejects_duplicates_and_invalid_period() -> None:
    with pytest.raises(ValidationError):
        BalanceQueryRequest(account_ids=["acc_001", "acc_001"])
    with pytest.raises(ValidationError):
        TransactionQueryRequest(
            account_ids=["acc_001"],
            start_date=date(2026, 7, 16),
            end_date=date(2026, 7, 1),
        )


@pytest.mark.asyncio
async def test_read_tools_register_once_and_invoke_with_common_context() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _success({"balance_results": []})

    async with httpx.AsyncClient(
        base_url="http://backend.test",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        tools = BackendAgentTools(BackendToolClient(_config(), client=http_client))
        registry = ContractToolRegistry(WorkflowContractStore())
        register_read_backend_agent_tools(registry, tools)
        result = await registry.invoke_by_tool(
            "query_balances",
            ContractToolCall(
                execution_context_id="exec_123",
                request_id="req_registry_123",
                arguments={"account_ids": ["acc_001"]},
            ),
        )

    assert result == {"balance_results": []}
    assert captured[0].headers["x-execution-context-id"] == "exec_123"
    assert captured[0].headers["x-request-id"] == "req_registry_123"
    assert registry.missing_contracts_for_workflow("wf_balance_inquiry") == set()
    assert registry.missing_contracts_for_workflow("wf_transaction_history") == set()
    assert registry.missing_contracts_for_workflow("wf_period_amount_summary") == set()


@pytest.mark.asyncio
async def test_registered_read_tool_rejects_invalid_workflow_arguments() -> None:
    async with httpx.AsyncClient(
        base_url="http://backend.test",
        transport=httpx.MockTransport(lambda _: _success({})),
    ) as http_client:
        tools = BackendAgentTools(BackendToolClient(_config(), client=http_client))
        registry = ContractToolRegistry(WorkflowContractStore())
        register_read_backend_agent_tools(registry, tools)

        with pytest.raises(ContractToolInputError) as raised:
            await registry.invoke_by_tool(
                "query_balances",
                ContractToolCall(
                    execution_context_id="exec_123",
                    request_id="req_invalid_123",
                    arguments={"account_ids": []},
                ),
            )

    assert raised.value.contract_id == "API-BALANCE-QUERY"
