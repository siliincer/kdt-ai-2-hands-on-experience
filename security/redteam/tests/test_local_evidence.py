import subprocess
import sys

from security.redteam.runner.local_evidence import workflow_evidence


def test_workflow_evidence_projects_bounded_business_state() -> None:
    trace = [
        {"step": f"step_{index}", "route_key": "next", "secret": "ignored"}
        for index in range(205)
    ]

    evidence = workflow_evidence(
        {
            "workflow_id": "wf_internal_transfer",
            "status": "waiting_approval",
            "execution_trace": trace,
            "data": {"account_id": "must-not-leak"},
        },
        "waiting_input",
    )

    assert evidence is not None
    assert evidence["observed_workflow_id"] == "wf_internal_transfer"
    assert evidence["runtime_status"] == "waiting_input"
    assert evidence["state_status"] == "waiting_approval"
    assert len(evidence["trace"]) == 200
    assert "data" not in evidence


def test_workflow_evidence_projects_global_terminal_state() -> None:
    assert workflow_evidence(None, "no_match") is None
    evidence = workflow_evidence(
        {
            "workflow_id": "wf_global_agent_entry",
            "status": "no_match",
            "current_step_id": "emit_no_matching_workflow",
            "route_key": "no_match",
        },
        "no_match",
    )
    assert evidence is not None
    assert evidence["trace"] == [
        {"step_id": "emit_no_matching_workflow", "route_key": "no_match"}
    ]


def test_workflow_evidence_discards_malformed_trace_values() -> None:
    evidence = workflow_evidence(
        {
            "workflow_id": "wf_balance_inquiry",
            "status": "x" * 101,
            "execution_trace": [
                None,
                {"step": ""},
                {"step": "valid", "route_key": ""},
                {"step": "kept", "route_key": "completed"},
            ],
        },
        "completed",
    )

    assert evidence is not None
    assert evidence["state_status"] == "completed"
    assert evidence["trace"] == [
        {"step_id": "valid", "route_key": None},
        {"step_id": "kept", "route_key": "completed"},
    ]


def test_workflow_evidence_business_sequence_and_global_entry_in_subprocess() -> None:
    code = """
from security.redteam.runner.local_evidence import workflow_evidence

statuses = ("waiting_approval", "waiting_authentication", "completed")
for status in statuses:
    evidence = workflow_evidence(
        {
            "workflow_id": "wf_internal_transfer",
            "status": status,
            "execution_trace": [{"step": status}],
        },
        "completed" if status == "completed" else "waiting_input",
    )
    assert evidence is not None
    assert evidence["state_status"] == status

global_evidence = workflow_evidence(
    {
        "workflow_id": "wf_global_agent_entry",
        "status": "no_match",
        "current_step_id": "emit_no_matching_workflow",
    },
    "no_match",
)
assert global_evidence is not None
assert global_evidence["trace"][-1]["step_id"] == "emit_no_matching_workflow"
"""

    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0, completed.stderr
