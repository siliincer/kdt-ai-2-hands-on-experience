"""Launch an isolated local Agent process for one red-team run."""

from __future__ import annotations

import json
import os
import re
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

from security.redteam.config import RedTeamConfig, is_loopback_hostname
from security.redteam.runner.client import RequestBudget
from security.redteam.runner.json_io import decode_bounded_json
from security.redteam.runner.reporter import redact


class ManagedAgentError(RuntimeError):
    """Raised when the isolated Agent process cannot be started safely."""


_DIRECT_OPENER = build_opener(ProxyHandler({}))
_INHERITED_ENV_KEYS = {
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "PATH",
    "PYTHONIOENCODING",
    "PYTHONUTF8",
    "TEMP",
    "TMP",
    "TMPDIR",
    "TZ",
}


def _log_tail(process_log, redact_fields: set[str]) -> str:
    process_log.seek(0)
    raw = process_log.read().decode("utf-8", errors="replace")[-4000:]
    sanitized = redact(raw, redact_fields)
    return sanitized if isinstance(sanitized, str) else ""


def _connection_target(config: RedTeamConfig) -> tuple[str, int]:
    parsed = urlparse(config.target.base_url)
    hostname = parsed.hostname
    if hostname is None or not is_loopback_hostname(hostname):
        raise ManagedAgentError("managed Agent requires a loopback target")
    host = "127.0.0.1" if hostname == "localhost" else hostname
    return host, parsed.port or 80


def _port_is_open(host: str, port: int, timeout: float = 0.1) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _read_ollama_json(
    request: str | Request,
    timeout: float,
    request_budget: RequestBudget,
    max_bytes: int,
) -> dict:
    bounded_timeout = request_budget.consume(timeout)
    try:
        with _DIRECT_OPENER.open(request, timeout=bounded_timeout) as response:
            payload = decode_bounded_json(
                iter(lambda: response.read(65_536), b""),
                max_bytes,
            )
    except (OSError, TimeoutError, URLError, json.JSONDecodeError, ValueError) as exc:
        raise ManagedAgentError("adaptive local QA requires the configured loopback Ollama server") from exc
    if not isinstance(payload, dict):
        raise ManagedAgentError("Ollama returned an invalid JSON response")
    return payload


def require_ollama_models(
    config: RedTeamConfig,
    request_budget: RequestBudget,
    required_models: set[str],
) -> dict[str, str]:
    endpoint = f"{config.safety.required_ollama_base_url}/api/tags"
    timeout = min(config.target.request_timeout_seconds, 10)
    payload = _read_ollama_json(
        endpoint,
        timeout,
        request_budget,
        config.adaptive_attack.max_response_bytes,
    )

    models = payload.get("models", []) if isinstance(payload, dict) else []
    installed: dict[str, str | None] = {}
    for item in models:
        if not isinstance(item, dict):
            continue
        digest = item.get("digest")
        normalized_digest = digest if isinstance(digest, str) else None
        for value in (item.get("name"), item.get("model")):
            if isinstance(value, str):
                installed[value] = normalized_digest
    if not required_models:
        raise ManagedAgentError("Ollama preflight requires at least one model")
    missing_models = required_models - set(installed)
    if missing_models:
        raise ManagedAgentError(
            "adaptive local QA requires each configured Ollama model: " + ", ".join(sorted(missing_models))
        )

    valid_digests: dict[str, str] = {}
    invalid_digests = set()
    for model in required_models:
        digest = installed[model]
        if digest is None or not re.fullmatch(r"[0-9a-f]{64}", digest):
            invalid_digests.add(model)
        else:
            valid_digests[model] = digest
    if invalid_digests:
        raise ManagedAgentError(
            "configured Ollama models are missing valid digests: " + ", ".join(sorted(invalid_digests))
        )

    for model in sorted(required_models):
        probe_body = json.dumps(
            {
                "model": model,
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
        probe = _read_ollama_json(
            probe_request,
            timeout,
            request_budget,
            config.adaptive_attack.max_response_bytes,
        )
        try:
            structured_response = json.loads(probe.get("response", ""))
        except (TypeError, json.JSONDecodeError) as exc:
            raise ManagedAgentError("Ollama structured-output probe failed") from exc
        if not isinstance(structured_response, dict):
            raise ManagedAgentError("Ollama structured-output probe failed")
        if structured_response.get("ok") is not True:
            raise ManagedAgentError("Ollama structured-output probe failed")
    return valid_digests


def _require_ollama_model(
    config: RedTeamConfig,
    request_budget: RequestBudget,
) -> dict[str, str]:
    return require_ollama_models(
        config,
        request_budget,
        {
            config.safety.required_ollama_model,
            config.adaptive_attack.model,
            config.judgment.model,
        },
    )


def _wait_until_ready(
    process: subprocess.Popen,
    host: str,
    port: int,
    timeout_seconds: float,
    request_budget: RequestBudget,
    process_log,
    redact_fields: set[str],
) -> None:
    request_budget.check_deadline()
    remaining_seconds = request_budget.remaining_seconds
    bounded_timeout = min(timeout_seconds, remaining_seconds) if remaining_seconds is not None else timeout_seconds
    deadline = time.monotonic() + bounded_timeout
    while time.monotonic() < deadline:
        request_budget.check_deadline()
        if process.poll() is not None:
            raise ManagedAgentError(
                f"managed Agent exited during startup: {process.returncode}\n{_log_tail(process_log, redact_fields)}"
            )
        startup_remaining = max(0.0, deadline - time.monotonic())
        run_remaining = request_budget.remaining_seconds
        poll_timeout = min(
            0.1,
            startup_remaining,
            run_remaining if run_remaining is not None else startup_remaining,
        )
        if poll_timeout <= 0:
            break
        if _port_is_open(host, port, poll_timeout):
            return
        startup_remaining = max(0.0, deadline - time.monotonic())
        run_remaining = request_budget.remaining_seconds
        sleep_seconds = min(
            0.05,
            startup_remaining,
            run_remaining if run_remaining is not None else startup_remaining,
        )
        if sleep_seconds <= 0:
            break
        time.sleep(sleep_seconds)
    request_budget.check_deadline()
    raise ManagedAgentError(f"managed Agent startup timed out\n{_log_tail(process_log, redact_fields)}")


def _stop_process(process: subprocess.Popen) -> None:
    try:
        if process.poll() is not None:
            return
        process.terminate()
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
            process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ManagedAgentError("managed Agent forced shutdown failed") from exc
    except OSError as exc:
        raise ManagedAgentError("managed Agent shutdown failed") from exc


@contextmanager
def managed_agent(
    config: RedTeamConfig,
    request_budget: RequestBudget,
) -> Iterator[dict[str, str]]:
    """Run a fresh Agent with the in-memory bank for this invocation only."""
    host, port = _connection_target(config)
    request_budget.check_deadline()
    run_remaining = request_budget.remaining_seconds
    port_probe_timeout = min(
        0.1,
        run_remaining if run_remaining is not None else 0.1,
    )
    if _port_is_open(host, port, port_probe_timeout):
        raise ManagedAgentError(f"refusing to reuse an existing process on {host}:{port}")
    model_digests = _require_ollama_model(config, request_budget)

    environment = {key: value for key, value in os.environ.items() if key in _INHERITED_ENV_KEYS}
    environment["NO_PROXY"] = "localhost,127.0.0.1,::1"
    environment["no_proxy"] = "localhost,127.0.0.1,::1"
    environment["BANK_CLIENT"] = config.safety.required_bank_client
    environment["LLM_PROVIDER"] = config.safety.required_llm_provider
    environment["OLLAMA_BASE_URL"] = config.safety.required_ollama_base_url
    environment["OLLAMA_MODEL"] = config.safety.required_ollama_model
    environment["LLM_MODEL"] = config.safety.required_ollama_model
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
    try:
        process_log = tempfile.TemporaryFile()
    except OSError as exc:
        raise ManagedAgentError("managed Agent log creation failed") from exc

    process = None
    active_error: BaseException | None = None
    try:
        try:
            process = subprocess.Popen(
                command,
                env=environment,
                stdout=process_log,
                stderr=subprocess.STDOUT,
            )
        except OSError as exc:
            raise ManagedAgentError("managed Agent process start failed") from exc
        try:
            _wait_until_ready(
                process,
                host,
                port,
                config.execution.agent_startup_timeout_seconds,
                request_budget,
                process_log,
                config.safety.redact_fields,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ManagedAgentError("managed Agent startup check failed") from exc
        yield model_digests
    except BaseException as exc:
        active_error = exc
        raise
    finally:
        cleanup_error: ManagedAgentError | None = None
        try:
            if process is not None:
                _stop_process(process)
        except ManagedAgentError as exc:
            cleanup_error = exc
        try:
            process_log.close()
        except OSError as exc:
            log_error = ManagedAgentError("managed Agent log cleanup failed")
            log_error.__cause__ = exc
            cleanup_error = cleanup_error or log_error
        if cleanup_error is not None:
            if active_error is None:
                raise cleanup_error
            active_error.add_note(f"managed Agent cleanup also failed: {cleanup_error}")
