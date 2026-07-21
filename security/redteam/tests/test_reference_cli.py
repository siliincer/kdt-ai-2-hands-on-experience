import argparse
import subprocess
from pathlib import Path

import pytest

import security.redteam.runner.reference_cli as reference_cli
from security.redteam.config import load_config
from security.redteam.runner.managed_agent import ManagedAgentError
from security.redteam.runner.reference_cases import MAX_REFERENCE_CASE_BYTES
from security.redteam.runner.reporter import ReportWriteError

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("value", ["", "xyz", "a" * 65, "ABCDEF1"])
def test_reference_cli_rejects_invalid_source_commit(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        reference_cli._commit(value)


def test_reference_cli_resolves_existing_commit_and_rejects_missing_commit() -> None:
    expected = subprocess.run(
        ["git", "rev-parse", "origin/main"],
        cwd=ROOT.parents[1],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert reference_cli._resolve_commit(expected[:7]) == expected
    with pytest.raises(argparse.ArgumentTypeError, match="does not exist"):
        reference_cli._resolve_commit("deadbee")


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
