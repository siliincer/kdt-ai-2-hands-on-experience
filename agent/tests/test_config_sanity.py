"""재생성된 config YAML 정합성 검증 (시트 v2 기준)."""

from __future__ import annotations

import yaml

from agent.paths import WORKFLOWS_PATH
from agent.subgraph_builder import SYSTEM_KEYS, build_all_workflow_graphs


def _load_workflows() -> dict:
    with open(WORKFLOWS_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def test_workflows_yaml_loads_with_expected_ids():
    workflows = _load_workflows()
    assert "wf_balance_inquiry" in workflows
    assert "wf_external_transfer" in workflows
    assert "wf_global_agent_entry" in workflows


def test_balance_output_keys_are_namespaced_or_system():
    """balance 스텝의 output_data_key는 빈 값 / dotted / 시스템 키만 허용."""
    workflows = _load_workflows()
    for step in workflows["wf_balance_inquiry"]["steps"]:
        key = step.get("output_data_key") or ""
        assert not key or "." in key or key in SYSTEM_KEYS, (
            f"스텝 '{step['step_id']}'의 output_data_key '{key}'가 "
            "flat 업무 키로 남아 있음 (sync 매핑 누락)"
        )


def test_balance_routes_reference_existing_steps():
    workflows = _load_workflows()
    wf = workflows["wf_balance_inquiry"]
    step_ids = {s["step_id"] for s in wf["steps"]}
    for route in wf["routes"]:
        assert route["from_step_id"] in step_ids
        assert route["to_step_id"] == "END" or route["to_step_id"] in step_ids


def test_transfer_output_keys_are_namespaced_or_system():
    workflows = _load_workflows()
    for step in workflows["wf_external_transfer"]["steps"]:
        key = step.get("output_data_key") or ""
        assert not key or "." in key or key in SYSTEM_KEYS


def test_input_steps_have_output_keys():
    """input 스텝은 답변 저장 위치(output_data_key)가 반드시 있어야 한다.

    (ask_recipient는 시트에 비어 있어 sync가 Tool_v2에서 백필한다.)
    """
    workflows = _load_workflows()
    for wf_id in ("wf_balance_inquiry", "wf_external_transfer"):
        for step in workflows[wf_id]["steps"]:
            if step["step_type"] == "input":
                assert step.get("output_data_key"), (
                    f"[{wf_id}] input 스텝 '{step['step_id']}'에 output_data_key가 없음"
                )
    ask = next(
        s
        for s in workflows["wf_external_transfer"]["steps"]
        if s["step_id"] == "ask_recipient"
    )
    assert ask["output_data_key"] == "transfer.recipient"


def test_guardrail_rules_schema():
    """모든 가드레일 규칙이 엔진이 이해하는 형태인지 검증한다."""
    from agent.workflow_loader import get_guardrail_rules

    valid_actions = {
        "block",
        "require_additional_auth",
        "require_approval",
        "warn",
        "ask_clarification",
        "info_masking",
    }
    for rule_id, rule in get_guardrail_rules().items():
        assert rule.get("applies_to_scope") in {"global", "workflow", "tool"}, rule_id
        assert rule.get("action") in valid_actions, rule_id
        condition = rule.get("condition") or {}
        assert condition.get("contains_any") or condition.get("expression"), (
            f"규칙 '{rule_id}'에 엔진이 평가할 수 있는 condition이 없음"
        )


def test_all_workflows_compile_despite_missing_tools():
    """transfer는 미구현 tool을 참조하지만 서브그래프 컴파일은 성공해야 한다.

    (미등록 tool은 런타임에 route_key='error'로 안전하게 실패한다.)
    """
    graphs = build_all_workflow_graphs()
    assert "wf_balance_inquiry" in graphs
    assert "wf_external_transfer" in graphs
    assert "wf_global_agent_entry" in graphs
