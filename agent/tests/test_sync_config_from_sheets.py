"""관리시트의 검토용 컬럼과 런타임 YAML의 경계를 검증한다."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

AGENT_DIR = Path(__file__).resolve().parents[1]
SYNC_SCRIPT = AGENT_DIR / "scripts" / "sync_config_from_sheets.py"


def _load_sync_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "sync_config_from_sheets",
        SYNC_SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("관리시트 동기화 스크립트를 불러올 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_step_management_columns_are_not_exported_to_runtime_yaml() -> None:
    sync_module = _load_sync_module()
    row = {
        "step_id": "request_recipient_selection",
        "step_type": "input",
        "interaction_mode": "webhook_then_resume",
        "backend_api_path": "/api/v1/agent-tools/recipients:resolve",
        "prompt_for": "legacy_prompt",
    }

    assert sync_module._convert_row(row, "steps") == {
        "step_id": "request_recipient_selection",
        "step_type": "input",
    }


def test_management_column_filter_is_limited_to_workflow_steps() -> None:
    sync_module = _load_sync_module()

    assert sync_module._convert_row(
        {"tool_id": "resolve_recipient", "backend_api_path": "/recipients:resolve"},
        "tools",
    ) == {
        "tool_id": "resolve_recipient",
        "backend_api_path": "/recipients:resolve",
    }
