import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import security.redteam.runner.compare as compare_module
from security.redteam.config import load_config
from security.redteam.models import ComparisonRun, Verdict
from security.redteam.runner.client import RequestBudgetError

ROOT = Path(__file__).resolve().parents[1]


def test_comparison_runs_full_unique_matrix_and_writes_aggregate(
    monkeypatch,
    tmp_path,
):
    args = SimpleNamespace(
        scenario="prompt_injection",
        config=ROOT / "config.example.yaml",
        user_id="user_001",
        output_dir=tmp_path,
        generator_models=["qwen2.5:3b", "qwen2.5:3b", "gemma3:4b"],
        target_models=["qwen3:4b"],
        judgment_models=["mistral:7b"],
        seeds=[7, 7, 11],
        seed_profile=None,
    )

    class _Parser:
        @staticmethod
        def parse_args():
            return args

    calls = []

    def fake_run(config, scenario_name, _user_id, output_dir):
        key = (
            config.adaptive_attack.model,
            config.safety.required_ollama_model,
            config.adaptive_attack.seed,
            scenario_name,
        )
        calls.append(key)
        stem = f"run-{len(calls)}"
        paths = (output_dir / f"{stem}.json", output_dir / f"{stem}.md")
        paths[0].write_text(
            json.dumps(
                {
                    "results": [{"verdict": "PASS"}],
                    "attacker_telemetry": {
                        "requests": 2,
                        "attempts": 2,
                        "successes": 2,
                        "failures": 0,
                        "rejected_out_of_scope": 0,
                        "rejected_duplicates": 0,
                    },
                    "llm_telemetry": {"attempts": 3, "failures": 0},
                    "judgment_telemetry": {
                        "attempts": 3,
                        "failures": 0,
                        "disagreements": 1,
                        "uncertain": 0,
                    },
                    "review_required": True,
                }
            ),
            encoding="utf-8",
        )
        paths[1].write_text("report", encoding="utf-8")
        return Verdict.PASS, paths

    monkeypatch.setattr(compare_module, "_parser", lambda: _Parser())
    monkeypatch.setattr(compare_module, "_run_named_scenario", fake_run)

    assert compare_module.main() == 0
    assert len(calls) == 4
    assert len(set(calls)) == 4
    aggregate_paths = list(tmp_path.glob("comparison_*.json"))
    assert len(aggregate_paths) == 1
    payload = json.loads(aggregate_paths[0].read_text(encoding="utf-8"))
    assert payload["total_runs"] == 4
    assert payload["verdict_counts"] == {"ERROR": 0, "FAIL": 0, "PASS": 4}
    assert len(payload["runs"]) == 4
    assert payload["runs"][0]["generator_successes"] == 2
    assert payload["runs"][0]["target_attempts"] == 3
    assert payload["runs"][0]["judgment_disagreements"] == 1
    assert payload["runs"][0]["review_required"] is True
    assert len(payload["model_summaries"]) == 4
    assert len(payload["combination_summaries"]) == 2
    assert all(
        summary["seeds"] == [7, 11]
        and summary["stable_verdict"] == "PASS"
        and summary["verdict_consistency_rate"] == 1.0
        and summary["review_required_rate"] == 1.0
        for summary in payload["combination_summaries"]
    )
    summaries = {
        (summary["role"], summary["model"]): summary
        for summary in payload["model_summaries"]
    }
    target_summary = summaries[("target", "qwen3:4b")]
    assert target_summary["run_verdict_counts"] == {
        "ERROR": 0,
        "FAIL": 0,
        "PASS": 4,
    }
    assert "verdict_counts" not in target_summary
    assert target_summary["target_contract_pass_rate"] == 1.0
    assert target_summary["target_contract_fail_rate"] == 0.0
    assert target_summary["target_contract_error_rate"] == 0.0
    assert target_summary["target_llm_failure_rate"] == 0.0
    judgment_summary = summaries[("judgment", "mistral:7b")]
    assert judgment_summary["judgment_agreement_rate"] == pytest.approx(2 / 3)
    assert judgment_summary["judgment_disagreement_rate"] == pytest.approx(1 / 3)
    assert judgment_summary["judgment_uncertain_rate"] == 0.0
    assert judgment_summary["judgment_failure_rate"] == 0.0
    markdown_path = aggregate_paths[0].with_suffix(".md")
    assert markdown_path.is_file()
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "candidate acceptance" in markdown
    assert "contract PASS" in markdown
    assert "rule agreement" in markdown
    assert "Seed Stability" in markdown
    assert "stable PASS" in markdown
    assert "Role rate" not in markdown
    assert aggregate_paths[0].with_suffix(".complete").is_file()


def test_comparison_rejects_matrix_over_limit(monkeypatch, tmp_path):
    args = SimpleNamespace(
        scenario="all",
        config=ROOT / "config.example.yaml",
        user_id="user_001",
        output_dir=tmp_path,
        generator_models=[f"generator-{index}" for index in range(13)],
        target_models=["target"],
        seeds=[1],
    )

    class _Parser:
        @staticmethod
        def parse_args():
            return args

    monkeypatch.setattr(compare_module, "_parser", lambda: _Parser())
    monkeypatch.setattr(
        compare_module,
        "_run_named_scenario",
        lambda *_args: (_ for _ in ()).throw(AssertionError("must not run")),
    )

    assert compare_module.main() == 2
    reports = list(tmp_path.glob("*-execution_error.json"))
    assert len(reports) == 1
    payload = json.loads(reports[0].read_text(encoding="utf-8"))
    assert payload["stage"] == "comparison_setup"
    assert payload["verdict"] == "ERROR"


def test_comparison_redacts_custom_field_from_setup_stdout(
    monkeypatch,
    capsys,
    tmp_path,
):
    args = SimpleNamespace(
        scenario="prompt_injection",
        config=ROOT / "config.example.yaml",
        user_id="user_001",
        output_dir=tmp_path,
        generator_models=None,
        target_models=None,
        judgment_models=None,
        seeds=None,
        seed_profile=None,
    )
    config = load_config(args.config)
    raw = config.model_dump(mode="python")
    raw["safety"]["redact_fields"].add("demo_private")
    config = type(config).model_validate(raw)

    class _Parser:
        @staticmethod
        def parse_args():
            return args

    def fail_matrix(*_args, **_kwargs):
        raise ValueError("demo_private=visible-value")

    monkeypatch.setattr(compare_module, "_parser", lambda: _Parser())
    monkeypatch.setattr(compare_module, "load_config", lambda _path: config)
    monkeypatch.setattr(compare_module, "_matrix_size", fail_matrix)

    assert compare_module.main() == 2
    stdout = capsys.readouterr().out
    rendered = next(tmp_path.glob("*-execution_error.json")).read_text()
    assert "visible-value" not in stdout
    assert "visible-value" not in rendered
    assert "[REDACTED]" in stdout


def test_comparison_contains_aggregate_finalization_timeout(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    args = SimpleNamespace(
        scenario="prompt_injection",
        config=ROOT / "config.example.yaml",
        user_id="user_001",
        output_dir=tmp_path,
        generator_models=["generator-model"],
        target_models=["target-model"],
        judgment_models=["judgment-model"],
        seeds=[7],
        seed_profile=None,
    )

    class _Parser:
        @staticmethod
        def parse_args():
            return args

    def fake_run(_config, _scenario, _user_id, output_dir):
        json_path = output_dir / "run.json"
        markdown_path = output_dir / "run.md"
        json_path.write_text('{"report_type":"execution_error"}', encoding="utf-8")
        markdown_path.write_text("error report", encoding="utf-8")
        return Verdict.ERROR, (json_path, markdown_path)

    def fail_report(*args, **kwargs):
        del args, kwargs
        raise RequestBudgetError("deadline exhausted")

    monkeypatch.setattr(compare_module, "_parser", lambda: _Parser())
    monkeypatch.setattr(compare_module, "_run_named_scenario", fake_run)
    monkeypatch.setattr(compare_module, "write_comparison_report", fail_report)

    assert compare_module.main() == 2
    assert "failed to write comparison report" in capsys.readouterr().out


def test_comparison_run_rejects_overlapping_judgment_counts():
    with pytest.raises(
        ValidationError,
        match="comparison judgment result counts exceed attempts",
    ):
        ComparisonRun(
            scenario_name="prompt_injection",
            generator_model="generator",
            target_model="target",
            judgment_model="judge",
            seed=1,
            verdict=Verdict.PASS,
            duration_seconds=1,
            report_json="report.json",
            report_markdown="report.md",
            result_counts={verdict: 0 for verdict in Verdict},
            generator_requests=1,
            generator_attempts=1,
            generator_successes=1,
            generator_rejections=0,
            generator_failures=0,
            target_attempts=1,
            target_failures=0,
            judgment_attempts=1,
            judgment_failures=0,
            judgment_disagreements=1,
            judgment_uncertain=1,
            review_required=True,
        )


def test_seed_profiles_are_fixed_and_do_not_mix_with_explicit_seeds():
    assert compare_module._selected_seeds(None, "screening", 42) == [7, 42, 99]
    assert compare_module._selected_seeds(None, "final", 42) == [
        7,
        19,
        42,
        73,
        99,
    ]
    assert compare_module._selected_seeds([7, 7, 11], None, 42) == [7, 11]
    assert compare_module._selected_seeds(None, None, 42) == [42]
    with pytest.raises(ValueError, match="cannot be combined"):
        compare_module._selected_seeds([7], "screening", 42)
