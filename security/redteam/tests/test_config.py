from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from security.redteam.config import RedTeamConfig, load_config, load_scenario

ROOT = Path(__file__).resolve().parents[1]


def test_example_config_allows_only_local_agent():
    config = load_config(ROOT / "config.example.yaml")

    assert config.target.base_url == "http://localhost:8001"
    assert config.safety.allow_remote_targets is False
    assert config.safety.required_bank_client == "local"
    assert config.safety.required_llm_provider == "ollama"
    assert config.safety.required_ollama_model == "qwen2.5:3b"
    assert config.adaptive_attack.model == "qwen2.5:3b"
    assert config.adaptive_attack.max_iterations_per_attack == 3
    assert config.adaptive_attack.max_generation_attempts == 5
    assert config.adaptive_attack.candidates_per_generation == 3
    assert config.adaptive_attack.seed == 42


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
    assert len(scenario.attacks) == 3
    for attack in scenario.attacks:
        assert attack.adaptive is True
        assert len(attack.candidate_required_patterns) == 2
        assert attack.expected_ledger is not None
        assert attack.expected_ledger.unchanged
    assert scenario.expected_response.allowed_statuses == {"blocked", "no_match"}


def test_approval_scenario_has_multi_turn_contract():
    scenario = load_scenario(ROOT / "scenarios" / "approval_bypass.yaml")

    assert scenario.id == "wf_ab_approval_bypass"
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
    ] == [
        0,
        None,
        1,
    ]
    final_expectation = scenario.attacks[-1].expected_ledger
    assert final_expectation is not None
    assert final_expectation.balance_deltas == {"acc_001": -50000}
