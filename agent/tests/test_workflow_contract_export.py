"""관리시트에서 생성한 Workflow 계약 Manifest 검증."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parents[1]
EXPORT_SCRIPT = AGENT_DIR / "scripts" / "export_workflow_contracts.py"
MANIFEST_PATH = AGENT_DIR / "contracts" / "workflow-contracts.json"


def _load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_generated_workflow_contract_is_current() -> None:
    result = subprocess.run(
        [sys.executable, str(EXPORT_SCRIPT), "--check"],
        cwd=AGENT_DIR,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_manifest_contains_canonical_workflows_and_contracts() -> None:
    manifest = _load_manifest()

    assert len(manifest["workflows"]) == 9
    assert len(manifest["contracts"]) == 50
    assert "wf_global_agent_entry" in manifest["workflows"]
    assert "wf_external_transfer" in manifest["workflows"]
    assert "API-EXTERNAL-TRANSFER-EXECUTE" in manifest["contracts"]
    assert "UI-RECIPIENT-SELECT" in manifest["contracts"]


def test_manifest_uses_current_hitl_contract() -> None:
    manifest = _load_manifest()
    external_transfer = manifest["workflows"]["wf_external_transfer"]
    recipient_step = next(
        step
        for step in external_transfer["steps"]
        if step["step_id"] == "request_recipient_selection"
    )

    assert recipient_step["interaction_mode"] == "webhook_then_resume"
    assert recipient_step["contract_id"] == "UI-RECIPIENT-SELECT"
    assert "to_recipient_candidate_id" in recipient_step["output_state_keys"]
    assert all(
        mapping["state_key"] != "prompt_for"
        for mapping in external_transfer["step_data_mappings"]
    )


def test_exporter_can_show_single_workflow() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(EXPORT_SCRIPT),
            "--workflow",
            "wf_balance_inquiry",
        ],
        cwd=AGENT_DIR,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    workflow = json.loads(result.stdout)
    assert workflow["catalog"]["workflow_id"] == "wf_balance_inquiry"
    workflow_contract_ids = {
        step["contract_id"] for step in workflow["steps"] if step["contract_id"]
    }
    assert workflow_contract_ids >= {
        "API-ACCOUNT-LIST",
        "API-BALANCE-QUERY",
    }
