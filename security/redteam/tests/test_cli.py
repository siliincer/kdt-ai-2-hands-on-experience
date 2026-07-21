import argparse
import json
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import security.redteam.runner.cli as cli_module
from security.redteam.config import load_config
from security.redteam.models import Verdict
from security.redteam.runner.cli import (
    ALL_SCENARIOS,
    EXIT_CODES,
    REGRESSION_SCENARIOS,
    _canonical_sha256,
    _model_name,
    _reproducibility_metadata,
    _scenario_names,
    _seed,
    _with_model,
    _with_model_overrides,
)
from security.redteam.runner.client import RequestBudgetError
from security.redteam.runner.managed_agent import ManagedAgentError

ROOT = Path(__file__).resolve().parents[1]


def test_exit_codes_distinguish_security_failure_from_execution_error():
    assert EXIT_CODES == {
        Verdict.PASS: 0,
        Verdict.FAIL: 1,
        Verdict.ERROR: 2,
    }


def test_legacy_helper_updates_only_generator_model():
    config = load_config(ROOT / "config.example.yaml")

    updated = _with_model(config, "gemma3:4b")

    assert updated.adaptive_attack.model == "gemma3:4b"
    assert updated.safety.required_ollama_model == (
        "hf.co/QuantFactory/Llama-3-8B-Instruct-Finance-RAG-GGUF:Q4_K_M"
    )
    assert updated.judgment.model == "llama3.2:3b"
    assert config.adaptive_attack.model == "exaone3.5:7.8b"


def test_model_name_rejects_shell_metacharacters():
    with pytest.raises(argparse.ArgumentTypeError, match="unsupported characters"):
        _model_name("qwen;echo")


def test_split_model_and_seed_overrides_are_independent():
    config = load_config(ROOT / "config.example.yaml")

    updated = _with_model_overrides(
        config,
        generator_model="llama3.2:3b",
        target_model="qwen3:4b",
        judgment_model="gemma3:4b",
        seed=27,
    )

    assert updated.adaptive_attack.model == "llama3.2:3b"
    assert updated.safety.required_ollama_model == "qwen3:4b"
    assert updated.adaptive_attack.seed == 27
    assert updated.judgment.model == "gemma3:4b"


def test_combined_and_split_model_overrides_are_mutually_exclusive():
    config = load_config(ROOT / "config.example.yaml")

    with pytest.raises(ValueError, match="disabled"):
        _with_model_overrides(
            config,
            model="qwen2.5:3b",
            target_model="qwen3:4b",
        )


@pytest.mark.parametrize("value", ["-1", "2147483648", "not-a-number"])
def test_seed_rejects_invalid_values(value):
    with pytest.raises(argparse.ArgumentTypeError):
        _seed(value)


def test_reproducibility_metadata_separates_models_and_hashes_inputs(monkeypatch):
    config = _with_model_overrides(
        load_config(ROOT / "config.example.yaml"),
        generator_model="llama3.2:3b",
        target_model="qwen3:4b",
        judgment_model="gemma3:4b",
        seed=27,
    )
    scenario = cli_module.load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    monkeypatch.setattr(cli_module, "_git_state", lambda: ("c" * 40, True))

    metadata = _reproducibility_metadata(
        config,
        scenario,
        {
            "llama3.2:3b": "a" * 64,
            "qwen3:4b": "b" * 64,
            "gemma3:4b": "c" * 64,
        },
    )

    assert metadata.generator_model == "llama3.2:3b"
    assert metadata.generator_model_digest == "a" * 64
    assert metadata.target_model == "qwen3:4b"
    assert metadata.target_model_digest == "b" * 64
    assert metadata.judgment_model == "gemma3:4b"
    assert metadata.judgment_model_digest == "c" * 64
    assert metadata.seed == 27
    assert len(metadata.config_sha256) == 64
    assert len(metadata.scenario_sha256) == 64
    assert metadata.git_commit == "c" * 40
    assert metadata.git_dirty is True


def test_canonical_hash_is_stable_for_set_order():
    first = {"values": {"gamma", "alpha", "beta"}, "nested": [{"b", "a"}]}
    second = {"nested": [{"a", "b"}], "values": {"beta", "gamma", "alpha"}}

    assert _canonical_sha256(first) == _canonical_sha256(second)


def test_scenario_profiles_resolve_to_existing_unique_files():
    assert _scenario_names("all") == ALL_SCENARIOS
    assert _scenario_names("regression") == REGRESSION_SCENARIOS
    assert _scenario_names("prompt_injection") == ("prompt_injection",)
    assert len(ALL_SCENARIOS) == len(set(ALL_SCENARIOS))
    assert set(REGRESSION_SCENARIOS) < set(ALL_SCENARIOS)
    assert all(
        (ROOT / "scenarios" / f"{name}.yaml").is_file() for name in ALL_SCENARIOS
    )


def test_cli_converts_managed_agent_error_to_report(monkeypatch, capsys, tmp_path):
    config_path = ROOT / "config.example.yaml"
    args = SimpleNamespace(
        scenario="prompt_injection",
        config=config_path,
        user_id="user_001",
        output_dir=tmp_path,
        model=None,
    )

    class _Parser:
        @staticmethod
        def parse_args():
            return args

    @contextmanager
    def fail_managed_agent(*_args, **_kwargs):
        raise ManagedAgentError("synthetic lifecycle failure")
        yield

    monkeypatch.setattr(cli_module, "_parser", lambda: _Parser())
    monkeypatch.setattr(cli_module, "managed_agent", fail_managed_agent)

    assert cli_module.main() == 2
    output = capsys.readouterr().out
    assert "synthetic lifecycle failure" in output
    reports = list(tmp_path.glob("*-execution_error.json"))
    assert len(reports) == 1
    assert reports[0].with_suffix(".md").is_file()
    assert reports[0].with_suffix(".complete").is_file()
    payload = json.loads(reports[0].read_text(encoding="utf-8"))
    assert payload["stage"] == "scenario_execution"
    assert payload["error_type"] == "ManagedAgentError"
    assert payload["verdict"] == "ERROR"


def test_cli_records_config_error_with_default_redaction(monkeypatch, capsys, tmp_path):
    args = SimpleNamespace(
        scenario="prompt_injection",
        config=tmp_path / "missing.yaml",
        user_id="user_001",
        output_dir=tmp_path,
        model=None,
    )

    class _Parser:
        @staticmethod
        def parse_args():
            return args

    def fail_config(_path):
        raise ValueError("token=super-secret")

    monkeypatch.setattr(cli_module, "_parser", lambda: _Parser())
    monkeypatch.setattr(cli_module, "load_config", fail_config)

    assert cli_module.main() == 2
    assert "Error report:" in capsys.readouterr().out
    reports = list(tmp_path.glob("*-execution_error.json"))
    assert len(reports) == 1
    rendered = reports[0].read_text(encoding="utf-8")
    assert "super-secret" not in rendered
    assert "[REDACTED]" in rendered
    payload = json.loads(rendered)
    assert payload["stage"] == "config_loading"


def test_cli_records_malformed_yaml_as_config_error(monkeypatch, tmp_path):
    config_path = tmp_path / "malformed.yaml"
    config_path.write_text("execution: [", encoding="utf-8")
    args = SimpleNamespace(
        scenario="prompt_injection",
        config=config_path,
        user_id="user_001",
        output_dir=tmp_path,
        model=None,
    )

    class _Parser:
        @staticmethod
        def parse_args():
            return args

    monkeypatch.setattr(cli_module, "_parser", lambda: _Parser())

    assert cli_module.main() == 2
    report = next(tmp_path.glob("*-execution_error.json"))
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["stage"] == "config_loading"
    assert payload["error_type"] == "ValueError"
    assert report.with_suffix(".complete").is_file()


def test_cli_contains_error_report_finalization_timeout(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    def fail_report(*args, **kwargs):
        del args, kwargs
        raise RequestBudgetError("deadline exhausted")

    monkeypatch.setattr(cli_module, "write_execution_error_report", fail_report)

    paths = cli_module._record_cli_error(
        scenario_name="prompt_injection",
        stage="scenario_execution",
        error=RuntimeError("synthetic failure"),
        started_at=datetime.now(UTC),
        started_monotonic=0,
        output_dir=tmp_path,
        redact_fields={"token"},
        finalization_timeout_seconds=0.01,
    )

    assert paths is None
    assert "failed to write execution error report" in capsys.readouterr().out


def test_cli_redacts_custom_field_from_execution_stdout(monkeypatch, capsys, tmp_path):
    args = SimpleNamespace(
        scenario="prompt_injection",
        config=ROOT / "config.example.yaml",
        user_id="user_001",
        output_dir=tmp_path,
        model=None,
    )
    config = load_config(args.config)
    raw = config.model_dump(mode="python")
    raw["safety"]["redact_fields"].add("demo_private")
    config = type(config).model_validate(raw)

    class _Parser:
        @staticmethod
        def parse_args():
            return args

    def fail_run(*_args, **_kwargs):
        raise ManagedAgentError("demo_private=visible-value")

    monkeypatch.setattr(cli_module, "_parser", lambda: _Parser())
    monkeypatch.setattr(cli_module, "load_config", lambda _path: config)
    monkeypatch.setattr(cli_module, "_run_named_scenario", fail_run)

    assert cli_module.main() == 2
    stdout = capsys.readouterr().out
    rendered = next(tmp_path.glob("*-execution_error.json")).read_text()
    assert "visible-value" not in stdout
    assert "visible-value" not in rendered
    assert "[REDACTED]" in stdout


def test_cli_redacts_custom_field_before_config_validation(
    monkeypatch,
    capsys,
    tmp_path,
) -> None:
    raw = yaml.safe_load((ROOT / "config.example.yaml").read_text(encoding="utf-8"))
    raw["safety"]["redact_fields"].append("demo_private")
    raw["target"]["request_timeout_seconds"] = "demo_private=visible-value"
    config_path = tmp_path / "invalid-config.yaml"
    config_path.write_text(
        yaml.safe_dump(raw, allow_unicode=True),
        encoding="utf-8",
    )
    args = SimpleNamespace(
        scenario="prompt_injection",
        config=config_path,
        output_dir=tmp_path,
    )

    class _Parser:
        @staticmethod
        def parse_args():
            return args

    monkeypatch.setattr(cli_module, "_parser", lambda: _Parser())

    assert cli_module.main() == 2
    stdout = capsys.readouterr().out
    rendered = next(tmp_path.glob("*-execution_error.json")).read_text()
    assert "visible-value" not in stdout
    assert "visible-value" not in rendered
    assert "[REDACTED]" in stdout


def test_batch_profile_runs_every_scenario_and_keeps_highest_exit_code(
    monkeypatch, capsys
):
    config_path = ROOT / "config.example.yaml"
    args = SimpleNamespace(
        scenario="regression",
        config=config_path,
        user_id="user_001",
        output_dir=ROOT / "reports",
        model=None,
    )

    class _Parser:
        @staticmethod
        def parse_args():
            return args

    calls = []

    def fake_run(_config, scenario_name, _user_id, output_dir):
        calls.append(scenario_name)
        verdict = Verdict.FAIL if scenario_name == "risk_manipulation" else Verdict.PASS
        return verdict, (output_dir / "result.json", output_dir / "result.md")

    monkeypatch.setattr(cli_module, "_parser", lambda: _Parser())
    monkeypatch.setattr(cli_module, "_run_named_scenario", fake_run)

    assert cli_module.main() == 1
    assert calls == list(REGRESSION_SCENARIOS)
    assert "FAIL: risk_manipulation" in capsys.readouterr().out
