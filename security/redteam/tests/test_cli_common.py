from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from security.redteam.config import load_config
from security.redteam.runner.cli_common import (
    _canonical_sha256,
    _model_name,
    _with_model_overrides,
)

ROOT = Path(__file__).resolve().parents[1]


def test_model_name_rejects_shell_metacharacters() -> None:
    with pytest.raises(
        argparse.ArgumentTypeError,
        match="unsupported characters",
    ):
        _model_name("qwen;echo")


def test_model_role_overrides_are_independent() -> None:
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
    assert updated.judgment.model == "gemma3:4b"
    assert updated.adaptive_attack.seed == 27


def test_combined_model_override_is_rejected() -> None:
    config = load_config(ROOT / "config.example.yaml")

    with pytest.raises(ValueError, match="disabled"):
        _with_model_overrides(
            config,
            model="qwen2.5:3b",
        )


def test_canonical_hash_is_stable_for_set_order() -> None:
    first = {
        "values": {"gamma", "alpha", "beta"},
        "nested": [{"b", "a"}],
    }
    second = {
        "nested": [{"a", "b"}],
        "values": {"beta", "gamma", "alpha"},
    }

    assert _canonical_sha256(first) == _canonical_sha256(second)
