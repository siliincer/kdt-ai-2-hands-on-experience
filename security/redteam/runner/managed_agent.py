"""Launch an isolated local Agent process for one red-team run."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener

from security.redteam.config import RedTeamConfig
from security.redteam.models import ExecutionMode
from security.redteam.runner.reporter import redact


class ManagedAgentError(RuntimeError):
    """Raised when the isolated Agent process cannot be started safely."""


_DIRECT_OPENER = build_opener(ProxyHandler({}))


def _log_tail(process_log) -> str:
    process_log.seek(0)
    raw = process_log.read().decode("utf-8", errors="replace")[-4000:]
    sanitized = redact(raw, set())
    return sanitized if isinstance(sanitized, str) else ""


def _connection_target(config: RedTeamConfig) -> tuple[str, int]:
    parsed = urlparse(config.target.base_url)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ManagedAgentError("managed Agent requires a loopback target")
    return "127.0.0.1", parsed.port or 80


def _port_is_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.1):
            return True
    except OSError:
        return False


def _read_ollama_json(request: str | Request, timeout: float) -> dict:
    try:
        with _DIRECT_OPENER.open(request, timeout=timeout) as response:
            payload = json.load(response)
    except (OSError, TimeoutError, URLError, json.JSONDecodeError) as exc:
        raise ManagedAgentError(
            "llm_redteam requires the configured loopback Ollama server"
        ) from exc
    if not isinstance(payload, dict):
        raise ManagedAgentError("Ollama returned an invalid JSON response")
    return payload


def _require_ollama_model(config: RedTeamConfig) -> None:
    endpoint = f"{config.safety.required_ollama_base_url}/api/tags"
    timeout = min(config.target.request_timeout_seconds, 10)
    payload = _read_ollama_json(endpoint, timeout)

    models = payload.get("models", []) if isinstance(payload, dict) else []
    installed = {
        value
        for item in models
        if isinstance(item, dict)
        for value in (item.get("name"), item.get("model"))
        if isinstance(value, str)
    }
    if config.safety.required_ollama_model not in installed:
        raise ManagedAgentError(
            "llm_redteam requires the configured Ollama model to be installed"
        )

    probe_body = json.dumps(
        {
            "model": config.safety.required_ollama_model,
            "prompt": 'Return only JSON with {"ok": true}.',
            "stream": False,
            "format": {
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
            },
            "options": {"temperature": 0, "num_predict": 16},
        }
    ).encode("utf-8")
    probe_request = Request(
        f"{config.safety.required_ollama_base_url}/api/generate",
        data=probe_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    probe = _read_ollama_json(probe_request, timeout)
    try:
        structured_response = json.loads(probe.get("response", ""))
    except (TypeError, json.JSONDecodeError) as exc:
        raise ManagedAgentError("Ollama structured-output probe failed") from exc
    if structured_response.get("ok") is not True:
        raise ManagedAgentError("Ollama structured-output probe failed")


def _wait_until_ready(
    process: subprocess.Popen,
    host: str,
    port: int,
    timeout_seconds: float,
    process_log,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ManagedAgentError(
                f"managed Agent exited during startup: {process.returncode}\n"
                f"{_log_tail(process_log)}"
            )
        if _port_is_open(host, port):
            return
        time.sleep(0.05)
    raise ManagedAgentError(
        f"managed Agent startup timed out\n{_log_tail(process_log)}"
    )


@contextmanager
def managed_agent(config: RedTeamConfig) -> Iterator[None]:
    """Run a fresh Agent with the in-memory bank for this invocation only."""
    host, port = _connection_target(config)
    if _port_is_open(host, port):
        raise ManagedAgentError(
            f"refusing to reuse an existing process on {host}:{port}"
        )
    if config.execution.mode == ExecutionMode.LLM_REDTEAM:
        _require_ollama_model(config)

    environment = os.environ.copy()
    for key in tuple(environment):
        if key.lower().endswith("_proxy"):
            environment.pop(key)
    environment["NO_PROXY"] = "localhost,127.0.0.1,::1"
    environment["no_proxy"] = "localhost,127.0.0.1,::1"
    environment["BANK_CLIENT"] = config.safety.required_bank_client
    environment["LLM_PROVIDER"] = config.safety.required_llm_provider
    environment["OLLAMA_BASE_URL"] = config.safety.required_ollama_base_url
    environment["OLLAMA_MODEL"] = config.safety.required_ollama_model
    environment["LLM_MODEL"] = config.safety.required_ollama_model
    environment.pop("MOCK_FINANCIAL_SERVICE_URL", None)
    for key in (
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "LANGCHAIN_API_KEY",
        "LANGSMITH_API_KEY",
    ):
        environment[key] = ""
    environment["LANGCHAIN_TRACING_V2"] = "false"
    environment["LANGSMITH_TRACING"] = "false"
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "security.redteam.runner.local_agent_app:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    with tempfile.TemporaryFile() as process_log:
        process = subprocess.Popen(
            command,
            env=environment,
            stdout=process_log,
            stderr=subprocess.STDOUT,
        )
        try:
            _wait_until_ready(
                process,
                host,
                port,
                config.execution.agent_startup_timeout_seconds,
                process_log,
            )
            yield
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
