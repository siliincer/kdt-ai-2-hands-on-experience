import argparse
from pathlib import Path

import pytest

from security.redteam.config import load_config
from security.redteam.models import Verdict
from security.redteam.runner.cli import EXIT_CODES, _model_name, _with_model

ROOT = Path(__file__).resolve().parents[1]


def test_exit_codes_distinguish_security_failure_from_execution_error():
    assert EXIT_CODES == {
        Verdict.PASS: 0,
        Verdict.FAIL: 1,
        Verdict.ERROR: 2,
    }


def test_model_override_updates_generator_and_target_model():
    config = load_config(ROOT / "config.example.yaml")

    updated = _with_model(config, "llama3.2:3b")

    assert updated.adaptive_attack.model == "llama3.2:3b"
    assert updated.safety.required_ollama_model == "llama3.2:3b"
    assert config.adaptive_attack.model == "qwen2.5:3b"


def test_model_name_rejects_shell_metacharacters():
    with pytest.raises(argparse.ArgumentTypeError, match="unsupported characters"):
        _model_name("qwen;echo")
