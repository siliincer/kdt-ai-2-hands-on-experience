from __future__ import annotations

import io
import json
from pathlib import Path
from urllib.request import ProxyHandler

import pytest

import security.redteam.runner.managed_agent as managed
from security.redteam.config import load_config
from security.redteam.runner.client import RequestBudget


class _OllamaResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _config():
    root = Path(__file__).resolve().parents[1]
    return load_config(root / "config.example.yaml")


def _models_payload(
    *,
    digest: str | None = "a" * 64,
) -> bytes:
    models = []

    for name in (
        "exaone3.5:7.8b",
        ("hf.co/QuantFactory/Llama-3-8B-Instruct-Finance-RAG-GGUF:Q4_K_M"),
        "llama3.2:3b",
    ):
        item: dict[str, object] = {
            "name": name,
        }

        if digest is not None:
            item["digest"] = digest

        models.append(item)

    return json.dumps(
        {
            "models": models,
        }
    ).encode()


def test_ollama_probe_opener_has_no_proxy_handler():
    handlers = getattr(
        managed._DIRECT_OPENER,
        "handlers",
        [],
    )

    assert not any(isinstance(handler, ProxyHandler) for handler in handlers)


def test_managed_agent_only_runs_model_preflight(
    monkeypatch,
):
    config = _config()
    budget = RequestBudget(100)
    expected = {
        config.adaptive_attack.model: "a" * 64,
        config.safety.required_ollama_model: "b" * 64,
        config.judgment.model: "c" * 64,
    }
    calls = []

    def preflight(received_config, received_budget):
        calls.append(
            (
                received_config,
                received_budget,
            )
        )
        return expected

    monkeypatch.setattr(
        managed,
        "_require_ollama_model",
        preflight,
    )

    with managed.managed_agent(
        config,
        budget,
    ) as digests:
        assert digests == expected

    assert len(calls) == 1
    assert calls[0][0] is config
    assert calls[0][1] is budget
    assert not hasattr(
        managed,
        "_wait_until_ready",
    )
    assert not hasattr(
        managed,
        "_stop_process",
    )


def test_ollama_preflight_requires_configured_model(
    monkeypatch,
):
    config = _config()

    monkeypatch.setattr(
        managed,
        "_DIRECT_OPENER",
        type(
            "MissingModelOpener",
            (),
            {"open": lambda *args, **kwargs: _OllamaResponse(b'{"models":[{"name":"another-model:latest"}]}')},
        )(),
    )

    with pytest.raises(
        managed.ManagedAgentError,
        match="configured Ollama model",
    ):
        managed._require_ollama_model(
            config,
            RequestBudget(100),
        )


def test_ollama_preflight_rejects_response_over_byte_limit(
    monkeypatch,
):
    config = _config().model_copy(
        update={
            "adaptive_attack": (
                _config().adaptive_attack.model_copy(
                    update={
                        "max_response_bytes": 1024,
                    }
                )
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

    with pytest.raises(
        managed.ManagedAgentError,
        match="configured loopback",
    ):
        managed._require_ollama_model(
            config,
            RequestBudget(100),
        )


def test_ollama_preflight_accepts_configured_models(
    monkeypatch,
):
    config = _config()
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

    assert managed._require_ollama_model(
        config,
        budget,
    ) == {
        "exaone3.5:7.8b": "a" * 64,
        ("hf.co/QuantFactory/Llama-3-8B-Instruct-Finance-RAG-GGUF:Q4_K_M"): "a" * 64,
        "llama3.2:3b": "a" * 64,
    }

    assert budget.used == 4


def test_ollama_preflight_can_probe_reference_models_only(
    monkeypatch,
):
    config = _config()
    payload = json.dumps(
        {
            "models": [
                {
                    "name": config.adaptive_attack.model,
                    "digest": "a" * 64,
                },
                {
                    "name": config.judgment.model,
                    "digest": "b" * 64,
                },
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
        {
            config.adaptive_attack.model,
            config.judgment.model,
        },
    ) == {
        config.adaptive_attack.model: "a" * 64,
        config.judgment.model: "b" * 64,
    }

    assert budget.used == 3


def test_ollama_preflight_requires_model_digest(
    monkeypatch,
):
    config = _config()

    monkeypatch.setattr(
        managed,
        "_DIRECT_OPENER",
        type(
            "MissingDigestOpener",
            (),
            {"open": lambda *args, **kwargs: _OllamaResponse(_models_payload(digest=None))},
        )(),
    )

    with pytest.raises(
        managed.ManagedAgentError,
        match="valid digests",
    ):
        managed._require_ollama_model(
            config,
            RequestBudget(100),
        )


def test_ollama_preflight_rejects_failed_inference_probe(
    monkeypatch,
):
    config = _config()
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

    with pytest.raises(
        managed.ManagedAgentError,
        match="structured-output probe",
    ):
        managed._require_ollama_model(
            config,
            RequestBudget(100),
        )


@pytest.mark.parametrize(
    "structured_payload",
    [
        [],
        "text",
        1,
        None,
    ],
)
def test_ollama_preflight_rejects_non_object_probe(
    monkeypatch,
    structured_payload,
):
    config = _config()
    responses = iter(
        [
            _OllamaResponse(_models_payload()),
            _OllamaResponse(json.dumps({"response": json.dumps(structured_payload)}).encode()),
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

    with pytest.raises(
        managed.ManagedAgentError,
        match="structured-output probe",
    ):
        managed._require_ollama_model(
            config,
            RequestBudget(100),
        )
