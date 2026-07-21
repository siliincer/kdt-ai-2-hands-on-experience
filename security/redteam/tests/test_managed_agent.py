from __future__ import annotations

import io
import subprocess
from pathlib import Path
from urllib.request import ProxyHandler

import pytest

import security.redteam.runner.managed_agent as managed
from security.redteam.config import load_config
from security.redteam.models import ExecutionMode


class _FakeProcess:
    returncode = None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = 0

    def wait(self, timeout):
        return self.returncode

    def kill(self):
        self.returncode = -9


class _OllamaResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def test_ollama_probe_opener_has_no_proxy_handler():
    assert not any(isinstance(handler, ProxyHandler) for handler in managed._DIRECT_OPENER.handlers)


def test_managed_agent_forces_local_bank_and_cleans_up(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "config.example.yaml")
    process = _FakeProcess()
    captured = {}
    port_states = iter([False, True])

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["environment"] = kwargs["env"]
        return process

    monkeypatch.setenv("BANK_CLIENT", "http")
    monkeypatch.setenv("MOCK_FINANCIAL_SERVICE_URL", "http://example.com")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    monkeypatch.setenv("LANGSMITH_API_KEY", "trace-secret")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.example")
    monkeypatch.setenv("https_proxy", "http://proxy.example")
    monkeypatch.setenv("ALL_PROXY", "socks5://proxy.example")
    monkeypatch.setattr(managed, "_port_is_open", lambda *args: next(port_states))
    monkeypatch.setattr(
        managed,
        "_require_ollama_model",
        lambda config: pytest.fail("fallback mode must not require Ollama"),
    )
    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    with managed.managed_agent(config):
        assert process.poll() is None
        assert captured["environment"]["BANK_CLIENT"] == "local"
        assert "MOCK_FINANCIAL_SERVICE_URL" not in captured["environment"]
        assert captured["environment"]["LLM_PROVIDER"] == "ollama"
        assert captured["environment"]["OLLAMA_BASE_URL"] == ("http://127.0.0.1:11434")
        assert captured["environment"]["OLLAMA_MODEL"] == "qwen2.5:3b"
        assert captured["environment"]["LLM_MODEL"] == "qwen2.5:3b"
        assert captured["environment"]["OPENAI_API_KEY"] == ""
        assert captured["environment"]["LANGSMITH_API_KEY"] == ""
        assert captured["environment"]["LANGCHAIN_TRACING_V2"] == "false"
        assert captured["environment"]["LANGSMITH_TRACING"] == "false"
        assert "HTTP_PROXY" not in captured["environment"]
        assert "https_proxy" not in captured["environment"]
        assert "ALL_PROXY" not in captured["environment"]
        assert captured["environment"]["NO_PROXY"] == "localhost,127.0.0.1,::1"
        assert captured["environment"]["no_proxy"] == "localhost,127.0.0.1,::1"

    assert process.returncode == 0
    assert captured["command"][2:4] == [
        "uvicorn",
        "security.redteam.runner.local_agent_app:app",
    ]


def test_llm_mode_requires_ollama_before_start(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "config.example.yaml")
    config = config.model_copy(
        update={"execution": config.execution.model_copy(update={"mode": ExecutionMode.LLM_REDTEAM})}
    )

    monkeypatch.setattr(managed, "_port_is_open", lambda *args: False)

    def unavailable(_config):
        raise managed.ManagedAgentError("Ollama unavailable")

    monkeypatch.setattr(managed, "_require_ollama_model", unavailable)
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda *args, **kwargs: pytest.fail("Agent must not start without Ollama"),
    )

    with pytest.raises(managed.ManagedAgentError, match="Ollama unavailable"):
        with managed.managed_agent(config):
            pass


def test_ollama_preflight_requires_configured_model(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "config.example.yaml")

    monkeypatch.setattr(
        managed,
        "_DIRECT_OPENER",
        type(
            "MissingModelOpener",
            (),
            {"open": lambda *args, **kwargs: _OllamaResponse(b'{"models":[{"name":"another-model:latest"}]}')},
        )(),
    )

    with pytest.raises(managed.ManagedAgentError, match="model to be installed"):
        managed._require_ollama_model(config)


def test_ollama_preflight_accepts_configured_model(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "config.example.yaml")
    responses = iter(
        [
            _OllamaResponse(b'{"models":[{"name":"qwen2.5:3b"}]}'),
            _OllamaResponse(b'{"response":"{\\"ok\\": true}"}'),
        ]
    )

    monkeypatch.setattr(
        managed,
        "_DIRECT_OPENER",
        type(
            "ReadyOpener",
            (),
            {"open": lambda *args, **kwargs: next(responses)},
        )(),
    )

    managed._require_ollama_model(config)


def test_ollama_preflight_rejects_failed_inference_probe(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "config.example.yaml")
    responses = iter(
        [
            _OllamaResponse(b'{"models":[{"name":"qwen2.5:3b"}]}'),
            _OllamaResponse(b'{"response":"not-json"}'),
        ]
    )

    monkeypatch.setattr(
        managed,
        "_DIRECT_OPENER",
        type(
            "FailedProbeOpener",
            (),
            {"open": lambda *args, **kwargs: next(responses)},
        )(),
    )

    with pytest.raises(managed.ManagedAgentError, match="structured-output probe"):
        managed._require_ollama_model(config)
