from __future__ import annotations

import io
import json
import subprocess
import tempfile
from pathlib import Path
from typing import cast
from urllib.request import ProxyHandler

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

import security.redteam.runner.managed_agent as managed
from security.redteam.config import load_config
from security.redteam.runner.client import RequestBudget, RequestBudgetError
from security.redteam.runner.local_policy import (
    LOCAL_POLICY_MARKER,
    inject_policy_marker,
)


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


class _FailingTerminateProcess(_FakeProcess):
    def terminate(self):
        raise PermissionError("synthetic terminate failure")


class _OllamaResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _models_payload(*, digest: str | None = "a" * 64) -> bytes:
    models = []
    for name in (
        "exaone3.5:7.8b",
        "hf.co/QuantFactory/Llama-3-8B-Instruct-Finance-RAG-GGUF:Q4_K_M",
        "llama3.2:3b",
    ):
        item = {"name": name}
        if digest is not None:
            item["digest"] = digest
        models.append(item)
    return json.dumps({"models": models}).encode()


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


@pytest.mark.parametrize("host", ["127.0.0.2", "127.255.255.254"])
def test_managed_agent_accepts_full_ipv4_loopback_range(host):
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "config.example.yaml")
    config = config.model_copy(
        update={
            "target": config.target.model_copy(
                update={"base_url": f"http://{host}:8001"}
            )
        }
    )

    assert managed._connection_target(config) == (host, 8001)


def test_local_policy_marker_is_injected_into_supported_inputs():
    text = inject_policy_marker("hello")
    messages = inject_policy_marker([HumanMessage(content="hello")])

    assert isinstance(text, str)
    assert LOCAL_POLICY_MARKER in text
    assert isinstance(messages, list)
    assert isinstance(messages[0], SystemMessage)
    assert LOCAL_POLICY_MARKER in str(messages[0].content)
    assert isinstance(messages[1], HumanMessage)


@pytest.mark.parametrize("mode", ["exit", "timeout"])
def test_managed_startup_logs_use_configured_redaction(monkeypatch, mode):
    process = _FakeProcess()
    timeout = 0.001
    if mode == "exit":
        process.returncode = 3
        timeout = 1
    monkeypatch.setattr(managed, "_port_is_open", lambda *args: False)

    with tempfile.TemporaryFile() as process_log:
        process_log.write(b"session_hint=private-value")
        with pytest.raises(managed.ManagedAgentError) as exc_info:
            managed._wait_until_ready(
                cast(subprocess.Popen, process),
                "127.0.0.1",
                8001,
                timeout,
                RequestBudget(10, max_seconds=2),
                process_log,
                {"session_hint"},
            )

    assert "private-value" not in str(exc_info.value)
    assert "[REDACTED]" in str(exc_info.value)


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
        assert captured["environment"]["OLLAMA_MODEL"] == (
            "hf.co/QuantFactory/Llama-3-8B-Instruct-Finance-RAG-GGUF:Q4_K_M"
        )
        assert captured["environment"]["LLM_MODEL"] == (
            "hf.co/QuantFactory/Llama-3-8B-Instruct-Finance-RAG-GGUF:Q4_K_M"
        )
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


def _prepare_managed_process_test(monkeypatch):
    monkeypatch.setattr(managed, "_port_is_open", lambda *args: False)
    monkeypatch.setattr(managed, "_require_ollama_model", lambda *args: None)
    monkeypatch.setattr(managed, "_wait_until_ready", lambda *args: None)


def test_managed_agent_wraps_log_creation_error(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "config.example.yaml")
    _prepare_managed_process_test(monkeypatch)

    def fail_log_creation():
        raise PermissionError("synthetic log failure")

    monkeypatch.setattr(tempfile, "TemporaryFile", fail_log_creation)

    with pytest.raises(managed.ManagedAgentError, match="log creation failed"):
        with managed.managed_agent(config, RequestBudget(100)):
            pass


def test_managed_agent_wraps_process_start_error(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "config.example.yaml")
    _prepare_managed_process_test(monkeypatch)

    def fail_start(*args, **kwargs):
        raise PermissionError("synthetic start failure")

    monkeypatch.setattr(subprocess, "Popen", fail_start)

    with pytest.raises(managed.ManagedAgentError, match="process start failed"):
        with managed.managed_agent(config, RequestBudget(100)):
            pass


def test_managed_agent_wraps_cleanup_error(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "config.example.yaml")
    _prepare_managed_process_test(monkeypatch)
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda *args, **kwargs: _FailingTerminateProcess(),
    )

    with pytest.raises(managed.ManagedAgentError, match="shutdown failed"):
        with managed.managed_agent(config, RequestBudget(100)):
            pass


def test_cleanup_error_does_not_mask_active_error(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "config.example.yaml")
    _prepare_managed_process_test(monkeypatch)
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda *args, **kwargs: _FailingTerminateProcess(),
    )

    with pytest.raises(ValueError, match="primary failure") as captured:
        with managed.managed_agent(config, RequestBudget(100)):
            raise ValueError("primary failure")

    assert any("cleanup also failed" in note for note in captured.value.__notes__)


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


def test_ollama_preflight_rejects_response_over_byte_limit(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "config.example.yaml")
    config = config.model_copy(
        update={
            "adaptive_attack": config.adaptive_attack.model_copy(
                update={"max_response_bytes": 1024}
            )
        }
    )
    monkeypatch.setattr(
        managed,
        "_DIRECT_OPENER",
        type(
            "OversizedOpener",
            (),
            {"open": lambda *args, **kwargs: _OllamaResponse(b"x" * 1025)},
        )(),
    )

    with pytest.raises(managed.ManagedAgentError, match="configured loopback"):
        managed._require_ollama_model(config, RequestBudget(100))


def test_ollama_preflight_accepts_configured_model(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "config.example.yaml")
    responses = iter(
        [
            _OllamaResponse(_models_payload()),
            _OllamaResponse(b'{"response":"{\\"ok\\": true}"}'),
            _OllamaResponse(b'{"response":"{\\"ok\\": true}"}'),
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
    assert managed._require_ollama_model(config, budget) == {
        "exaone3.5:7.8b": "a" * 64,
        "hf.co/QuantFactory/Llama-3-8B-Instruct-Finance-RAG-GGUF:Q4_K_M": "a" * 64,
        "llama3.2:3b": "a" * 64,
    }
    assert budget.used == 4


def test_ollama_preflight_can_probe_only_models_used_by_reference_run(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "config.example.yaml")
    payload = json.dumps(
        {
            "models": [
                {"name": config.adaptive_attack.model, "digest": "a" * 64},
                {"name": config.judgment.model, "digest": "b" * 64},
            ]
        }
    ).encode()
    responses = iter(
        [
            _OllamaResponse(payload),
            _OllamaResponse(b'{"response":"{\\"ok\\": true}"}'),
            _OllamaResponse(b'{"response":"{\\"ok\\": true}"}'),
        ]
    )
    monkeypatch.setattr(
        managed,
        "_DIRECT_OPENER",
        type(
            "ReferenceReadyOpener",
            (),
            {"open": lambda *args, **kwargs: next(responses)},
        )(),
    )

    budget = RequestBudget(100)
    assert managed.require_ollama_models(
        config,
        budget,
        {config.adaptive_attack.model, config.judgment.model},
    ) == {
        config.adaptive_attack.model: "a" * 64,
        config.judgment.model: "b" * 64,
    }
    assert budget.used == 3


def test_ollama_preflight_requires_model_digest(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "config.example.yaml")
    monkeypatch.setattr(
        managed,
        "_DIRECT_OPENER",
        type(
            "MissingDigestOpener",
            (),
            {
                "open": lambda *args, **kwargs: _OllamaResponse(
                    _models_payload(digest=None)
                )
            },
        )(),
    )

    with pytest.raises(managed.ManagedAgentError, match="valid digests"):
        managed._require_ollama_model(config, RequestBudget(100))


def test_ollama_preflight_rejects_failed_inference_probe(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "config.example.yaml")
    responses = iter(
        [
            _OllamaResponse(_models_payload()),
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
            _OllamaResponse(_models_payload()),
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
                set(),
            )

    assert clock[0] == pytest.approx(run_deadline)
    assert poll_timeouts
    assert max(poll_timeouts) <= run_deadline
