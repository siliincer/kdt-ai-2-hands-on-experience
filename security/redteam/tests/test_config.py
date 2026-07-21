from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from security.redteam.config import RedTeamConfig, load_config, load_scenario
from security.redteam.models import ExpectedResponse, Scenario

ROOT = Path(__file__).resolve().parents[1]


def test_reply_patterns_reject_nested_quantifiers() -> None:
    with pytest.raises(ValidationError, match="unsafe regex"):
        ExpectedResponse(
            allowed_statuses={"blocked"},
            forbidden_reply_patterns=[r"(a+)+$"],
        )


def test_config_loader_rejects_oversized_yaml_before_parsing(tmp_path) -> None:
    path = tmp_path / "oversized.yaml"
    path.write_text("#" + ("x" * 262_144), encoding="utf-8")

    with pytest.raises(ValueError, match="exceeds"):
        load_config(path)


def test_example_config_allows_only_local_agent():
    config = load_config(ROOT / "config.example.yaml")

    assert config.target.base_url == "http://localhost:8001"
    assert config.target.request_timeout_seconds == 60
    assert config.target.max_response_bytes == 1_048_576
    assert config.safety.allow_remote_targets is False
    assert config.safety.required_bank_client == "local"
    assert config.safety.required_llm_provider == "ollama"
    assert config.safety.required_ollama_model == (
        "hf.co/QuantFactory/Llama-3-8B-Instruct-Finance-RAG-GGUF:Q4_K_M"
    )
    assert config.adaptive_attack.model == "exaone3.5:7.8b"
    assert config.judgment.model == "llama3.2:3b"
    assert config.judgment.max_attempts_per_evaluation == 2
    assert config.adaptive_attack.max_iterations_per_attack == 3
    assert config.adaptive_attack.max_generation_attempts == 5
    assert config.adaptive_attack.candidates_per_generation == 3
    assert config.adaptive_attack.duplicate_similarity_threshold == 0.88
    assert config.adaptive_attack.seed == 42
    assert config.execution.max_requests_per_run == 350
    assert config.execution.max_run_seconds == 1200
    assert config.execution.report_finalization_timeout_seconds == 10


def test_attack_case_rejects_unbounded_procedural_product() -> None:
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    attack = scenario.attacks[1]
    raw = attack.model_dump(mode="python")
    raw["procedural_variation_slots"] = [
        {f"choice_{index}_a", f"choice_{index}_b"} for index in range(13)
    ]

    with pytest.raises(ValidationError, match="too many combinations"):
        type(attack).model_validate(raw)


def test_version_one_config_uses_safe_response_limit_defaults():
    raw = yaml.safe_load((ROOT / "config.example.yaml").read_text())
    raw["target"].pop("max_response_bytes")
    raw["adaptive_attack"].pop("max_response_bytes")
    raw["judgment"].pop("max_attempts_per_evaluation")
    raw["execution"].pop("report_finalization_timeout_seconds")

    config = RedTeamConfig.model_validate(raw)

    assert config.target.max_response_bytes == 1_048_576
    assert config.adaptive_attack.max_response_bytes == 1_048_576
    assert config.judgment.max_attempts_per_evaluation == 2
    assert config.execution.report_finalization_timeout_seconds == 10


def test_scenario_rejects_unknown_target_workflow():
    raw = yaml.safe_load((ROOT / "scenarios" / "prompt_injection.yaml").read_text())
    raw["attacks"][0]["target_workflow_id"] = "wf_unknown"

    with pytest.raises(ValidationError):
        Scenario.model_validate(raw)


@pytest.mark.parametrize("version", [0, 2])
def test_config_rejects_unknown_versions(version):
    raw = yaml.safe_load((ROOT / "config.example.yaml").read_text())
    raw["version"] = version

    with pytest.raises(ValidationError):
        RedTeamConfig.model_validate(raw)


@pytest.mark.parametrize("candidate_count", [2, 3, 4, 5])
def test_output_token_limit_must_cover_configured_candidates(candidate_count):
    raw = yaml.safe_load((ROOT / "config.example.yaml").read_text())
    raw["adaptive_attack"]["candidates_per_generation"] = candidate_count
    raw["adaptive_attack"]["max_output_tokens"] = 128 * candidate_count - 1

    with pytest.raises(ValidationError, match="128 tokens per candidate"):
        RedTeamConfig.model_validate(raw)

    raw["adaptive_attack"]["max_output_tokens"] = 128 * candidate_count
    config = RedTeamConfig.model_validate(raw)
    assert config.adaptive_attack.max_output_tokens == 128 * candidate_count


@pytest.mark.parametrize("host", ["127.0.0.2", "127.255.255.254", "[::1]"])
def test_config_accepts_supported_loopback_range(host):
    raw = yaml.safe_load((ROOT / "config.example.yaml").read_text())
    raw["target"]["base_url"] = f"http://{host}:8001"
    raw["target"]["allowed_origins"] = [f"http://{host}:8001"]

    config = RedTeamConfig.model_validate(raw)

    assert config.target.base_url == f"http://{host}:8001"


def test_config_rejects_empty_canonical_redact_field(tmp_path):
    raw = yaml.safe_load((ROOT / "config.example.yaml").read_text())
    raw["safety"]["redact_fields"] = ["---"]
    path = tmp_path / "invalid-redact-field.yaml"
    path.write_text(yaml.safe_dump(raw))

    with pytest.raises(ValidationError, match="must contain letters or numbers"):
        load_config(path)


def test_config_normalizes_canonical_redact_field_duplicates(tmp_path):
    raw = yaml.safe_load((ROOT / "config.example.yaml").read_text())
    raw["safety"]["redact_fields"] = ["api-key", "api_key", "API KEY"]
    path = tmp_path / "normalized-redact-fields.yaml"
    path.write_text(yaml.safe_dump(raw))

    config = load_config(path)

    assert config.safety.redact_fields == {"apikey"}


def test_remote_target_is_rejected():
    raw = yaml.safe_load((ROOT / "config.example.yaml").read_text())
    raw["target"]["base_url"] = "http://example.com"
    raw["target"]["allowed_origins"] = ["http://example.com"]

    with pytest.raises(ValidationError, match="remote red-team targets are disabled"):
        RedTeamConfig.model_validate(raw)


def test_external_bank_client_cannot_be_enabled():
    raw = yaml.safe_load((ROOT / "config.example.yaml").read_text())
    raw["safety"]["required_bank_client"] = "http"

    with pytest.raises(ValidationError):
        RedTeamConfig.model_validate(raw)


def test_external_chat_endpoint_is_rejected():
    raw = yaml.safe_load((ROOT / "config.example.yaml").read_text())
    raw["target"]["chat_path"] = "http://example.com/chat"

    with pytest.raises(
        ValidationError, match="chat_path must be a local absolute path"
    ):
        RedTeamConfig.model_validate(raw)


def test_prompt_injection_scenario_contract():
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")

    assert scenario.id == "wf_pi_prompt_injection"
    assert scenario.category == "policy_boundary"
    assert {tag.value for tag in scenario.coverage} == {
        "policy_confidentiality",
        "role_claim",
        "state_integrity",
    }
    assert len(scenario.attacks) == 3
    for attack in scenario.attacks:
        assert attack.adaptive is True
        assert attack.candidate_required_patterns
        assert attack.variation_required_patterns
        assert attack.variation_forbidden_patterns
        assert attack.generation_guidance
        assert attack.expected_intent_action
        assert attack.expected_intent_target
        assert attack.expected_ledger is not None
        assert attack.expected_ledger.unchanged
    assert scenario.expected_response.allowed_statuses == {"blocked", "no_match"}


@pytest.mark.parametrize(
    ("field", "value"),
    [("version", 2), ("type", "unrelated_future_mode")],
)
def test_scenario_rejects_unknown_contract(field, value, tmp_path):
    raw = yaml.safe_load((ROOT / "scenarios" / "prompt_injection.yaml").read_text())
    raw[field] = value
    path = tmp_path / "future-scenario.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True))

    with pytest.raises(ValidationError):
        load_scenario(path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("category", "future_boundary"),
        ("coverage", ["future_evidence"]),
        ("coverage", []),
    ],
)
def test_scenario_rejects_unknown_or_empty_taxonomy(field, value, tmp_path):
    raw = yaml.safe_load((ROOT / "scenarios" / "prompt_injection.yaml").read_text())
    raw[field] = value
    path = tmp_path / "invalid-taxonomy.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True))

    with pytest.raises(ValidationError):
        load_scenario(path)


def test_approval_scenario_has_multi_turn_contract():
    scenario = load_scenario(ROOT / "scenarios" / "approval_bypass.yaml")

    assert scenario.id == "wf_ab_approval_bypass"
    assert scenario.category == "authorization_flow"
    assert [len(attack.expanded_turns()) for attack in scenario.attacks] == [1, 2, 3]
    assert [attack.adaptive for attack in scenario.attacks] == [True, True, False]
    assert all(
        attack.candidate_template and "{variation}" in attack.candidate_template
        for attack in scenario.attacks[:2]
    )
    expectations = [attack.expected_ledger for attack in scenario.attacks]
    assert all(expectation is not None for expectation in expectations)
    assert [
        expectation.audit_log_delta
        for expectation in expectations
        if expectation is not None
    ] == [0, 1, 1]
    final_expectation = scenario.attacks[-1].expected_ledger
    assert final_expectation is not None
    assert final_expectation.balance_deltas == {"acc_001": -50000}


def test_data_confidentiality_scenario_contract():
    scenario = load_scenario(ROOT / "scenarios" / "data_confidentiality.yaml")

    assert scenario.id == "wf_dl_data_leakage"
    assert scenario.category == "data_confidentiality"
    assert {tag.value for tag in scenario.coverage} == {
        "sensitive_response",
        "state_integrity",
    }
    assert len(scenario.attacks) == 2
    assert all(attack.enforce_procedural_variation for attack in scenario.attacks)
    assert all(attack.procedural_variation_slots for attack in scenario.attacks)
    assert all(
        attack.expected_ledger is not None and attack.expected_ledger.unchanged
        for attack in scenario.attacks
    )
    assert scenario.expected_response.forbid_financial_secrets is True


def test_tool_governance_scenario_contract():
    scenario = load_scenario(ROOT / "scenarios" / "tool_governance.yaml")

    assert scenario.id == "wf_ta_tool_abuse"
    assert scenario.category == "tool_governance"
    assert {tag.value for tag in scenario.coverage} == {
        "approval_sequence",
        "state_integrity",
        "tool_execution",
    }
    adaptive_cases = [attack for attack in scenario.attacks if attack.adaptive]
    assert len(adaptive_cases) == 2
    assert all(attack.enforce_procedural_variation for attack in adaptive_cases)
    assert all(
        attack.expected_ledger is not None and attack.expected_ledger.unchanged
        for attack in adaptive_cases
    )
    control = scenario.attacks[-1]
    assert control.adaptive is False
    assert control.expected_ledger is not None
    assert control.expected_ledger.balance_deltas == {"acc_001": -50000}


def test_conversation_state_scenario_contract():
    scenario = load_scenario(ROOT / "scenarios" / "conversation_state.yaml")

    assert scenario.id == "wf_cs_conversation_state"
    assert scenario.category == "conversation_state"
    assert {tag.value for tag in scenario.coverage} == {
        "approval_sequence",
        "multi_turn",
        "state_integrity",
    }
    adaptive = scenario.attacks[0]
    assert adaptive.adaptive is True
    assert adaptive.enforce_procedural_variation is True
    assert len(adaptive.turns) == 2
    assert adaptive.expected_ledger is not None
    assert adaptive.expected_ledger.unchanged is True
    assert adaptive.expected_ledger.audit_log_delta == 1
    assert adaptive.expected_ledger.audit_tool_ids == ["write_audit_log"]
    control = scenario.attacks[1]
    assert control.adaptive is False
    assert len(control.turns) == 2
    assert control.expected_ledger is not None
    assert control.expected_ledger.audit_log_delta == 1


def test_risk_manipulation_scenario_contract():
    scenario = load_scenario(ROOT / "scenarios" / "risk_manipulation.yaml")

    assert scenario.id == "wf_rm_risk_manipulation"
    assert scenario.category == "authorization_flow"
    assert {tag.value for tag in scenario.coverage} == {
        "approval_sequence",
        "role_claim",
        "state_integrity",
        "tool_execution",
    }
    adaptive_cases = [attack for attack in scenario.attacks if attack.adaptive]
    assert len(adaptive_cases) == 2
    assert all(attack.enforce_procedural_variation for attack in adaptive_cases)
    assert all(
        attack.expected_ledger is not None and attack.expected_ledger.unchanged
        for attack in adaptive_cases
    )
    control = scenario.attacks[-1]
    assert control.expected_ledger is not None
    assert control.expected_ledger.balance_deltas == {"acc_001": -50000}


def test_audit_log_tampering_scenario_contract():
    scenario = load_scenario(ROOT / "scenarios" / "audit_log_tampering.yaml")

    assert scenario.id == "wf_alt_audit_log_tampering"
    assert scenario.category == "tool_governance"
    assert {tag.value for tag in scenario.coverage} == {
        "state_integrity",
        "tool_execution",
    }
    adaptive_cases = [attack for attack in scenario.attacks if attack.adaptive]
    assert len(adaptive_cases) == 2
    assert all(
        attack.expected_ledger is not None
        and attack.expected_ledger.audit_log_delta == 0
        for attack in adaptive_cases
    )
    control = scenario.attacks[-1]
    assert control.expected_ledger is not None
    assert control.expected_ledger.audit_workflow_ids == ["wf_account_list"]
    assert control.expected_ledger.audit_tool_ids == ["write_audit_log"]


def test_multi_step_scenario_contract():
    scenario = load_scenario(ROOT / "scenarios" / "multi_step_attack.yaml")

    assert scenario.id == "wf_msa_multi_step_attack"
    assert scenario.category == "conversation_state"
    assert {tag.value for tag in scenario.coverage} == {
        "approval_sequence",
        "multi_turn",
        "state_integrity",
        "tool_execution",
    }
    adaptive_cases = [attack for attack in scenario.attacks if attack.adaptive]
    assert len(adaptive_cases) == 2
    assert [len(attack.turns) for attack in adaptive_cases] == [4, 3]
    first_ledger = adaptive_cases[0].expected_ledger
    second_ledger = adaptive_cases[1].expected_ledger
    assert first_ledger is not None and first_ledger.unchanged
    assert second_ledger is not None
    assert second_ledger.balance_deltas == {"acc_001": -50000}
    assert scenario.attacks[-1].adaptive is False


def test_terminal_status_requires_explicit_ui_and_prompt_contracts():
    with pytest.raises(ValidationError, match="explicit terminal UI and prompt"):
        ExpectedResponse(
            allowed_statuses={"waiting_input", "blocked"},
            terminal_statuses={"blocked"},
        )
