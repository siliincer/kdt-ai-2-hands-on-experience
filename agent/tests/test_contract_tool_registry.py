"""계약 기반 Tool Registry 테스트."""

from __future__ import annotations

import pytest

from agent.tools.contract_registry import (
    ContractToolCall,
    ContractToolRegistrationError,
    ContractToolRegistry,
)
from agent.workflow_contracts import WorkflowContractStore


async def _handler(_: ContractToolCall) -> dict[str, str]:
    return {"outcome": "resolved"}


def test_contract_store_returns_workflow_specific_api_contracts() -> None:
    store = WorkflowContractStore()

    assert store.required_contract_ids(
        "wf_balance_inquiry", contract_type="agent_tool_api"
    ) == {"API-ACCOUNT-LIST", "API-BALANCE-QUERY"}


def test_registry_rejects_duplicate_contract_and_tool_ids() -> None:
    registry = ContractToolRegistry(WorkflowContractStore())
    registry.register(
        contract_id="API-ACCOUNT-LIST",
        tool_id="fetch_accounts",
        handler=_handler,
    )

    with pytest.raises(ValueError, match="contract_id 구현이 중복"):
        registry.register(
            contract_id="API-ACCOUNT-LIST",
            tool_id="fetch_accounts_copy",
            handler=_handler,
        )
    with pytest.raises(ValueError, match="tool_id 구현이 중복"):
        registry.register(
            contract_id="API-BALANCE-QUERY",
            tool_id="fetch_accounts",
            handler=_handler,
        )


def test_registry_rejects_ui_contract() -> None:
    registry = ContractToolRegistry(WorkflowContractStore())

    with pytest.raises(ValueError, match="Agent Tool API 계약이 아닙니다"):
        registry.register(
            contract_id="UI-BALANCE-RESULT",
            tool_id="emit_balance_result",
            handler=_handler,
        )


def test_registry_reports_missing_workflow_contracts() -> None:
    registry = ContractToolRegistry(WorkflowContractStore())
    registry.register(
        contract_id="API-ACCOUNT-LIST",
        tool_id="fetch_accounts",
        handler=_handler,
    )

    assert registry.missing_contracts_for_workflow("wf_balance_inquiry") == {
        "API-BALANCE-QUERY"
    }


def test_registry_start_validation_fails_with_missing_contract_details() -> None:
    registry = ContractToolRegistry(WorkflowContractStore())
    registry.register(
        contract_id="API-ACCOUNT-LIST",
        tool_id="fetch_accounts",
        handler=_handler,
    )

    with pytest.raises(ContractToolRegistrationError) as captured:
        registry.validate_workflow_contracts(["wf_balance_inquiry"])

    assert captured.value.missing_by_workflow == {
        "wf_balance_inquiry": ("API-BALANCE-QUERY",)
    }
