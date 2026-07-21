from pathlib import Path

import yaml

from security.redteam.config import load_scenario
from security.redteam.models import BusinessWorkflow
from security.redteam.runner.cli import _canonical_sha256
from security.redteam.runner.reference_cases import load_reference_case

ROOT = Path(__file__).resolve().parents[1]

WORKFLOWS = {
    "wf_external_transfer",
    "wf_balance_inquiry",
    "wf_account_list",
    "wf_transaction_history",
    "wf_period_amount_summary",
    "wf_set_default_account",
    "wf_set_account_alias",
    "wf_internal_transfer",
}
METHODS = {
    "prompt_injection",
    "approval_bypass",
    "tool_governance",
    "data_confidentiality",
    "risk_manipulation",
    "audit_log_tampering",
    "multi_step_attack",
    "conversation_state",
}
STATUSES = {"not_applicable", "planned", "partial", "implemented"}


def _coverage() -> dict:
    value = yaml.safe_load((ROOT / "workflow_coverage.yaml").read_text())
    assert isinstance(value, dict)
    return value


def _reference_manifest() -> dict:
    value = yaml.safe_load((ROOT / "reference_evidence_manifest.yaml").read_text())
    assert isinstance(value, dict)
    return value


def test_workflow_coverage_declares_complete_eight_by_eight_matrix():
    manifest = _coverage()

    assert manifest["version"] == 1
    assert set(manifest["workflows"]) == WORKFLOWS
    assert set(manifest["methods"]) == METHODS
    assert set(manifest["coverage"]) == WORKFLOWS
    business_workflows = {workflow.value for workflow in BusinessWorkflow}
    assert business_workflows == {*WORKFLOWS, "wf_global_agent_entry"}

    cells = 0
    for workflow_id, methods in manifest["coverage"].items():
        assert workflow_id in WORKFLOWS
        assert set(methods) == METHODS
        cells += len(methods)
    assert cells == 64


def test_workflow_coverage_references_existing_scenarios_and_evidence():
    manifest = _coverage()
    attack_ids = {}
    attack_workflows = {}
    reference_cases = {
        case.id: case
        for case in (
            load_reference_case(path)
            for path in (ROOT / "reference_cases").glob("*.yaml")
        )
    }

    for method, filename in manifest["methods"].items():
        scenario = load_scenario(ROOT / "scenarios" / filename)
        assert scenario.id
        attack_ids[method] = {attack.id for attack in scenario.attacks}
        attack_workflows[method] = {
            attack.id: attack.target_workflow_id.value for attack in scenario.attacks
        }

    for workflow_id, methods in manifest["coverage"].items():
        for method, cell in methods.items():
            assert cell["status"] in STATUSES
            evidence = cell["evidence"]
            reference_evidence = cell.get("reference_evidence", [])
            assert isinstance(evidence, list)
            assert isinstance(reference_evidence, list)
            if cell["status"] in {"planned", "not_applicable"}:
                assert evidence == []
                assert reference_evidence == []
            else:
                assert evidence or reference_evidence
                if evidence:
                    assert set(evidence) <= attack_ids[method]
                    assert {
                        attack_workflows[method][attack_id] for attack_id in evidence
                    } == {workflow_id}
                if reference_evidence:
                    assert set(reference_evidence) <= set(reference_cases)
                    assert {
                        reference_cases[case_id].target_workflow_id.value
                        for case_id in reference_evidence
                    } == {workflow_id}

            rationale = cell.get("rationale")
            if cell["status"] == "not_applicable":
                assert isinstance(rationale, str) and rationale.strip()
            else:
                assert rationale is None


def test_completed_reference_manifest_matches_the_exact_case_set() -> None:
    manifest = _reference_manifest()
    cases = [
        load_reference_case(path)
        for path in sorted((ROOT / "reference_cases").glob("*.yaml"))
    ]

    assert manifest["version"] == 1
    assert manifest["status"] == "completed"
    assert manifest["agent_source_commit"] == (
        "e867ccb95283f1ff1db20a1ad46dd13e80616ebe"
    )
    assert manifest["verification_test"] == (
        "security/redteam/tests/test_agent_reference_integration.py"
    )
    assert manifest["case_ids"] == [case.id for case in cases]
    assert manifest["case_set_sha256"] == _canonical_sha256(cases)


def test_workflow_coverage_counts_only_meaningful_cells():
    manifest = _coverage()
    cells = [
        cell for methods in manifest["coverage"].values() for cell in methods.values()
    ]

    assert sum(cell["status"] != "not_applicable" for cell in cells) == 51
    assert sum(cell["status"] == "not_applicable" for cell in cells) == 13
    assert sum(cell["status"] == "partial" for cell in cells) == 32
    assert sum(cell["status"] == "implemented" for cell in cells) == 19
    assert sum(cell["status"] == "planned" for cell in cells) == 0

    read_workflows = {
        "wf_balance_inquiry",
        "wf_account_list",
        "wf_transaction_history",
        "wf_period_amount_summary",
    }
    expected_not_applicable = {
        (workflow, method)
        for workflow in read_workflows
        for method in {"approval_bypass", "risk_manipulation", "audit_log_tampering"}
    }
    expected_not_applicable.add(("wf_account_list", "multi_step_attack"))
    actual_not_applicable = {
        (workflow, method)
        for workflow, methods in manifest["coverage"].items()
        for method, cell in methods.items()
        if cell["status"] == "not_applicable"
    }
    assert actual_not_applicable == expected_not_applicable
