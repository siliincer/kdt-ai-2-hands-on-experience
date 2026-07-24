"""Validate local Ollama models before Agent V3 red-team runs."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener

from security.redteam.config import RedTeamConfig
from security.redteam.runner.client import RequestBudget
from security.redteam.runner.json_io import decode_bounded_json


class ManagedAgentError(RuntimeError):
    """Raised when the local model preflight cannot complete safely."""


_DIRECT_OPENER = build_opener(ProxyHandler({}))


def _read_ollama_json(
    request: str | Request,
    timeout: float,
    request_budget: RequestBudget,
    max_bytes: int,
) -> dict[str, object]:
    bounded_timeout = request_budget.consume(timeout)

    try:
        with _DIRECT_OPENER.open(
            request,
            timeout=bounded_timeout,
        ) as response:
            payload = decode_bounded_json(
                iter(lambda: response.read(65_536), b""),
                max_bytes,
            )
    except (
        OSError,
        TimeoutError,
        URLError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
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
    timeout = min(
        config.target.request_timeout_seconds,
        10,
    )

    payload = _read_ollama_json(
        endpoint,
        timeout,
        request_budget,
        config.adaptive_attack.max_response_bytes,
    )

    models = payload.get("models")
    if not isinstance(models, list):
        raise ManagedAgentError("Ollama returned an invalid model list")

    installed: dict[str, str | None] = {}

    for item in models:
        if not isinstance(item, dict):
            continue

        digest = item.get("digest")
        normalized_digest = digest if isinstance(digest, str) else None

        for value in (
            item.get("name"),
            item.get("model"),
        ):
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
    invalid_digests: set[str] = set()

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
                "prompt": ('Return only JSON with {"ok": true}.'),
                "stream": False,
                "format": {
                    "type": "object",
                    "properties": {
                        "ok": {
                            "type": "boolean",
                        }
                    },
                    "required": ["ok"],
                },
                "options": {
                    "temperature": 0,
                    "num_predict": 16,
                },
            }
        ).encode("utf-8")

        probe_request = Request(
            (f"{config.safety.required_ollama_base_url}/api/generate"),
            data=probe_body,
            headers={
                "Content-Type": "application/json",
            },
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
        except (
            TypeError,
            json.JSONDecodeError,
        ) as exc:
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


@contextmanager
def managed_agent(
    config: RedTeamConfig,
    request_budget: RequestBudget,
) -> Iterator[dict[str, str]]:
    """Preserve the runner interface without launching a legacy Agent."""

    yield _require_ollama_model(
        config,
        request_budget,
    )
