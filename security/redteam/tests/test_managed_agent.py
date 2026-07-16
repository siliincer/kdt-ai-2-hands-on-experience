from __future__ import annotations

import io
import json
import subprocess
import tempfile
from pathlib import Path
from typing import cast
from urllib.request import ProxyHandler

import pytest

import security.redteam.runner.managed_agent as managed
from security.redteam.config import load_config
from security.redteam.runner.client import RequestBudget, RequestBudgetError


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
    handlers = getattr(managed._DIRECT_OPENER, "handlers", [])
    assert not any(isinstance(handler, ProxyHandler) for handler in handlers)


def test_managed_agent_preserves_ipv6_loopback_target():
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "config.example.yaml")
    config = config.model_copy(
        update={
            "target": config.target.model_copy(update={"base_url": "http://[::1]:8001"})
        }
    )

    assert managed._connection_target(config) == ("::1", 8001)


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
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "github-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@example/db")
    monkeypatch.setattr(managed, "_port_is_open", lambda *args: next(port_states))
    monkeypatch.setattr(
        managed,
        "_require_ollama_model",
        lambda config, request_budget: None,
    )
    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    with managed.managed_agent(config, RequestBudget(100)):
        assert process.poll() is None
        assert captured["environment"]["BANK_CLIENT"] == "local"
        assert "MOCK_FINANCIAL_SERVICE_URL" not in captured["environment"]
        assert captured["environment"]["LLM_PROVIDER"] == "ollama"
        assert captured["environment"]["OLLAMA_BASE_URL"] == ("http://127.0.0.1:11434")
        assert captured["environment"]["OLLAMA_MODEL"] == "qwen2.5:3b"
        assert captured["environment"]["LLM_MODEL"] == "qwen2.5:3b"
        assert "OPENAI_API_KEY" not in captured["environment"]
        assert "LANGSMITH_API_KEY" not in captured["environment"]
        assert captured["environment"]["LANGCHAIN_TRACING_V2"] == "false"
        assert captured["environment"]["LANGSMITH_TRACING"] == "false"
        assert "HTTP_PROXY" not in captured["environment"]
        assert "https_proxy" not in captured["environment"]
        assert "ALL_PROXY" not in captured["environment"]
        assert "AWS_SECRET_ACCESS_KEY" not in captured["environment"]
        assert "GITHUB_TOKEN" not in captured["environment"]
        assert "ANTHROPIC_API_KEY" not in captured["environment"]
        assert "DATABASE_URL" not in captured["environment"]
        assert captured["environment"]["NO_PROXY"] == "localhost,127.0.0.1,::1"
        assert captured["environment"]["no_proxy"] == "localhost,127.0.0.1,::1"

    assert process.returncode == 0
    assert captured["command"][2:4] == [
        "uvicorn",
        "security.redteam.runner.local_agent_app:app",
    ]


def test_managed_agent_requires_ollama_before_start(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "config.example.yaml")
    monkeypatch.setattr(managed, "_port_is_open", lambda *args: False)

    def unavailable(_config, _request_budget):
        raise managed.ManagedAgentError("Ollama unavailable")

    monkeypatch.setattr(managed, "_require_ollama_model", unavailable)
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda *args, **kwargs: pytest.fail("Agent must not start without Ollama"),
    )

    with pytest.raises(managed.ManagedAgentError, match="Ollama unavailable"):
        with managed.managed_agent(config, RequestBudget(100)):
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
            {
                "open": lambda *args, **kwargs: _OllamaResponse(
                    b'{"models":[{"name":"another-model:latest"}]}'
                )
            },
        )(),
    )

    with pytest.raises(managed.ManagedAgentError, match="configured Ollama model"):
        managed._require_ollama_model(config, RequestBudget(100))


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

    budget = RequestBudget(100)
    managed._require_ollama_model(config, budget)
    assert budget.used == 2


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
        managed._require_ollama_model(config, RequestBudget(100))


@pytest.mark.parametrize("structured_payload", [[], "text", 1, None])
def test_ollama_preflight_rejects_non_object_probe(
    monkeypatch,
    structured_payload,
):
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "config.example.yaml")
    responses = iter(
        [
            _OllamaResponse(b'{"models":[{"name":"qwen2.5:3b"}]}'),
            _OllamaResponse(
                json.dumps({"response": json.dumps(structured_payload)}).encode("utf-8")
            ),
        ]
    )
    monkeypatch.setattr(
        managed,
        "_DIRECT_OPENER",
        type(
            "InvalidShapeOpener",
            (),
            {"open": lambda *args, **kwargs: next(responses)},
        )(),
    )

    with pytest.raises(managed.ManagedAgentError, match="structured-output probe"):
        managed._require_ollama_model(config, RequestBudget(100))


@pytest.mark.parametrize("run_deadline", [0.01, 0.073])
def test_managed_startup_honors_run_deadline(monkeypatch, run_deadline):
    clock = [0.0]
    poll_timeouts = []
    monkeypatch.setattr(managed.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        managed.time,
        "sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    monkeypatch.setattr(
        managed,
        "_port_is_open",
        lambda _host, _port, timeout: poll_timeouts.append(timeout) or False,
    )
    budget = RequestBudget(10, max_seconds=run_deadline)

    with tempfile.TemporaryFile() as process_log:
        with pytest.raises(RequestBudgetError, match="deadline exhausted"):
            managed._wait_until_ready(
                cast(subprocess.Popen, _FakeProcess()),
                "127.0.0.1",
                8001,
                1.0,
                budget,
                process_log,
            )

    assert clock[0] == pytest.approx(run_deadline)
    assert poll_timeouts
    assert max(poll_timeouts) <= run_deadline
