import argparse
import subprocess
from pathlib import Path

import pytest

import security.redteam.runner.reference_cli as reference_cli
from security.redteam.config import load_config
from security.redteam.runner.managed_agent import ManagedAgentError
from security.redteam.runner.reference_cases import (
    MAX_REFERENCE_CASE_BYTES,
    load_reference_case,
)
from security.redteam.runner.reporter import ReportWriteError

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("value", ["", "xyz", "a" * 65, "ABCDEF1"])
def test_reference_cli_rejects_invalid_source_commit(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        reference_cli._commit(value)


@pytest.mark.parametrize("value", ["0", "11", "1.5", "many"])
def test_reference_cli_rejects_invalid_iteration_count(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        reference_cli._iteration_count(value)


def test_reference_cli_overrides_iteration_count() -> None:
    args = argparse.Namespace(
        config=ROOT / "config.example.yaml",
        generator_model=None,
        judgment_model=None,
        max_iterations=7,
    )

    config = reference_cli._load_reference_config(args)

    assert config.adaptive_attack.max_iterations_per_attack == 7


@pytest.mark.parametrize("value", ["UPPER", "with-dash", "../case"])
def test_reference_cli_rejects_invalid_case_id(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        reference_cli._case_id(value)


def test_reference_cli_selects_one_case() -> None:
    cases = [load_reference_case(path) for path in sorted((ROOT / "reference_cases").glob("*.yaml"))[:2]]

    selected = reference_cli._select_cases(cases, cases[1].id)

    assert [case.id for case in selected] == [cases[1].id]
    with pytest.raises(ValueError, match="do not contain case id"):
        reference_cli._select_cases(cases, "missing_case")


def test_reference_cli_resolves_selected_file_before_loading_other_cases(
    tmp_path: Path,
) -> None:
    case_id = "account_list_generated_instruction_case"
    source = ROOT / "reference_cases" / f"{case_id}.yaml"
    (tmp_path / source.name).write_text(source.read_text(encoding="utf-8"))
    (tmp_path / "unrelated.yaml").write_text("not: [valid", encoding="utf-8")

    paths = reference_cli._case_paths(tmp_path, case_id)
    cases = [load_reference_case(path) for path in paths]

    assert paths == [tmp_path / f"{case_id}.yaml"]
    assert [case.id for case in cases] == [case_id]


def test_reference_request_plan_fits_dedicated_default_budget() -> None:
    config = load_config(ROOT / "config.example.yaml")
    cases = [load_reference_case(path) for path in sorted((ROOT / "reference_cases").glob("*.yaml"))]

    required = reference_cli._required_reference_requests(config, cases)

    assert required == 970
    assert required <= config.execution.max_reference_requests_per_run
    assert required > config.execution.max_requests_per_run


def test_reference_request_plan_counts_only_generated_model_calls() -> None:
    config = load_config(ROOT / "config.example.yaml")
    generated = load_reference_case(ROOT / "reference_cases" / "account_list_generated_instruction_case.yaml")
    fixed = load_reference_case(ROOT / "reference_cases" / "account_list_contract_baseline.yaml")

    assert reference_cli._required_reference_requests(config, [fixed]) == 4
    assert reference_cli._required_reference_requests(config, [generated]) == 46
    assert reference_cli._required_reference_requests(config, [fixed, generated]) == 46


def test_reference_request_plan_allows_six_default_iterations() -> None:
    config = load_config(ROOT / "config.example.yaml")
    raw = config.model_dump(mode="python")
    raw["adaptive_attack"]["max_iterations_per_attack"] = 6
    config = type(config).model_validate(raw)
    cases = [load_reference_case(path) for path in sorted((ROOT / "reference_cases").glob("*.yaml"))]

    assert reference_cli._required_reference_requests(config, cases) == 1936


def test_reference_cli_accepts_commit_format_without_assuming_runner_checkout() -> None:
    expected = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT.parents[1],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert reference_cli._resolve_commit(expected[:7]) == expected[:7]
    assert reference_cli._resolve_commit("deadbee") == "deadbee"


def test_reference_cli_records_execution_error_artifact(monkeypatch, tmp_path) -> None:
    args = argparse.Namespace(
        config=ROOT / "config.example.yaml",
        output_dir=tmp_path,
        generator_model=None,
        judgment_model=None,
    )

    class _Parser:
        def parse_args(self):
            return args

    async def fail(_args, _config):
        raise RuntimeError("synthetic reference failure")

    monkeypatch.setattr(reference_cli, "_parser", _Parser)
    monkeypatch.setattr(reference_cli, "_run", fail)

    assert reference_cli.main() == 2
    reports = list(tmp_path.glob("*-execution_error.json"))
    assert len(reports) == 1
    assert reports[0].with_suffix(".complete").is_file()


def test_reference_cli_records_yaml_directory_as_input_error(
    monkeypatch,
    tmp_path,
) -> None:
    cases_dir = tmp_path / "cases"
    output_dir = tmp_path / "reports"
    cases_dir.mkdir()
    (cases_dir / "not-a-file.yaml").mkdir()
    args = argparse.Namespace(
        config=ROOT / "config.example.yaml",
        cases_dir=cases_dir,
        output_dir=output_dir,
        generator_model=None,
        judgment_model=None,
        agent_source_commit="e867ccb",
    )

    class _Parser:
        def parse_args(self):
            return args

    monkeypatch.setattr(reference_cli, "_parser", _Parser)

    assert reference_cli.main() == 2
    report = next(output_dir.glob("*-execution_error.json"))
    assert report.with_suffix(".complete").is_file()


@pytest.mark.parametrize(
    ("error", "stage"),
    [
        (ValueError("bad case"), "input_validation"),
        (ManagedAgentError("Ollama unavailable"), "model_preflight"),
        (RuntimeError("latest Agent modules are required"), "agent_import"),
        (ReportWriteError("write failed"), "report_finalization"),
    ],
)
def test_reference_cli_classifies_error_artifact_stage(error, stage) -> None:
    assert reference_cli._error_stage(error) == stage


@pytest.mark.asyncio
async def test_reference_cli_rejects_empty_case_directory(tmp_path) -> None:
    args = argparse.Namespace(
        config=ROOT / "config.example.yaml",
        cases_dir=tmp_path,
        output_dir=tmp_path,
        generator_model=None,
        judgment_model=None,
        agent_source_commit="e867ccb",
    )

    with pytest.raises(ValueError, match="directory is empty"):
        await reference_cli._run(args)


@pytest.mark.asyncio
async def test_reference_cli_rejects_oversized_case_set_before_parsing(
    tmp_path,
) -> None:
    for index in range(21):
        (tmp_path / f"case_{index}.yaml").write_bytes(b"x" * MAX_REFERENCE_CASE_BYTES)
    args = argparse.Namespace(
        config=ROOT / "config.example.yaml",
        cases_dir=tmp_path,
        output_dir=tmp_path,
        generator_model=None,
        judgment_model=None,
        agent_source_commit="e867ccb",
    )

    with pytest.raises(ValueError, match="case files exceed"):
        await reference_cli._run(args)


def test_reference_cli_redacts_custom_field_from_stdout_and_report(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    args = argparse.Namespace(
        config=ROOT / "config.example.yaml",
        output_dir=tmp_path,
        generator_model=None,
        judgment_model=None,
    )
    config = load_config(args.config)
    raw = config.model_dump(mode="python")
    raw["safety"]["redact_fields"].add("demo_private")
    config = type(config).model_validate(raw)

    class _Parser:
        def parse_args(self):
            return args

    async def fail(_args, _config):
        raise ValueError("demo_private=visible-value")

    monkeypatch.setattr(reference_cli, "_parser", _Parser)
    monkeypatch.setattr(reference_cli, "_load_reference_config", lambda _args: config)
    monkeypatch.setattr(reference_cli, "_run", fail)

    assert reference_cli.main() == 2
    stdout = capsys.readouterr().out
    report = next(tmp_path.glob("*-execution_error.json")).read_text()
    markdown = next(tmp_path.glob("*-execution_error.md")).read_text()
    assert "visible-value" not in stdout
    assert "visible-value" not in report
    assert "visible-value" not in markdown
    assert "[REDACTED]" in stdout
