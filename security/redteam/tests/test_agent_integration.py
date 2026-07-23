"""Compatibility checks for the Agent V3 testing contract."""

from __future__ import annotations

from security.redteam.models import BusinessWorkflow
from security.redteam.runner.agent_reference import _load_agent_api

EXPECTED_TESTBED_WORKFLOWS = {
    BusinessWorkflow.ACCOUNT_LIST,
    BusinessWorkflow.BALANCE_INQUIRY,
    BusinessWorkflow.TRANSACTION_HISTORY,
    BusinessWorkflow.PERIOD_AMOUNT_SUMMARY,
    BusinessWorkflow.SET_DEFAULT_ACCOUNT,
    BusinessWorkflow.SET_ACCOUNT_ALIAS,
    BusinessWorkflow.INTERNAL_TRANSFER,
    BusinessWorkflow.EXTERNAL_TRANSFER,
}


def test_agent_v3_testing_contract_is_available() -> None:
    api = _load_agent_api()

    assert set(api.factories) == EXPECTED_TESTBED_WORKFLOWS
    assert callable(api.backend_config)
    assert callable(api.mock_backend)
    assert callable(api.contract_store)
    assert callable(api.resume_request)

    for factory in api.factories.values():
        assert callable(factory)


def test_agent_v3_source_is_read_from_current_checkout() -> None:
    api = _load_agent_api()

    assert len(api.source_commit) >= 40
    assert api.source_root.name == "kdt-ai-2-hands-on-experience"
    assert api.source_dirty is False


def test_global_entry_is_not_a_business_testbed() -> None:
    api = _load_agent_api()

    assert BusinessWorkflow.GLOBAL_AGENT_ENTRY not in api.factories
