"""Load and enforce the local-only red-team safety policy."""

from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from security.redteam.models import ExecutionMode


class TargetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str
    health_path: str = "/health"
    chat_path: str = "/chat"
    ledger_path: str = "/__local_test__/ledger"
    llm_telemetry_path: str = "/__local_test__/llm-telemetry"
    allowed_origins: set[str] = Field(min_length=1)
    request_timeout_seconds: float = Field(gt=0, le=60)

    @model_validator(mode="after")
    def validate_target(self) -> TargetConfig:
        origin = self.base_url.rstrip("/")
        allowed = {value.rstrip("/") for value in self.allowed_origins}
        if origin not in allowed:
            raise ValueError("target base_url is not present in allowed_origins")

        parsed = urlparse(origin)
        if parsed.scheme != "http" or not parsed.hostname or parsed.path:
            raise ValueError("target must be an HTTP origin without a path")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("target origin must not contain credentials or parameters")

        for name, path in (
            ("health_path", self.health_path),
            ("chat_path", self.chat_path),
            ("ledger_path", self.ledger_path),
            ("llm_telemetry_path", self.llm_telemetry_path),
        ):
            parsed_path = urlparse(path)
            if (
                not path.startswith("/")
                or path.startswith("//")
                or parsed_path.scheme
                or parsed_path.netloc
                or parsed_path.query
                or parsed_path.fragment
            ):
                raise ValueError(f"{name} must be a local absolute path")
        return self


class ExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_turns_per_scenario: int = Field(gt=0, le=20)
    max_requests_per_run: int = Field(gt=0, le=200)
    agent_startup_timeout_seconds: float = Field(gt=0, le=60)
    mode: ExecutionMode = ExecutionMode.GUARDRAIL_FALLBACK


class SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allow_remote_targets: Literal[False] = False
    required_bank_client: Literal["local"] = "local"
    required_llm_provider: Literal["ollama"] = "ollama"
    required_ollama_base_url: Literal["http://127.0.0.1:11434"] = "http://127.0.0.1:11434"
    required_ollama_model: str = Field(min_length=1, max_length=200)
    allowed_user_ids: set[str] = Field(min_length=1)
    redact_fields: set[str] = Field(default_factory=set)


class RedTeamConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    target: TargetConfig
    execution: ExecutionConfig
    safety: SafetyConfig

    @model_validator(mode="after")
    def require_local_target(self) -> RedTeamConfig:
        if self.safety.allow_remote_targets:
            return self

        hostname = urlparse(self.target.base_url).hostname
        if hostname == "localhost":
            return self
        try:
            if hostname and ipaddress.ip_address(hostname).is_loopback:
                return self
        except ValueError:
            pass
        raise ValueError("remote red-team targets are disabled")


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        data = yaml.safe_load(stream)
    if not isinstance(data, dict):
        raise ValueError(f"expected a YAML mapping: {path}")
    return data


def load_config(path: Path) -> RedTeamConfig:
    return RedTeamConfig.model_validate(_load_yaml(path))


def load_scenario(path: Path):
    from security.redteam.models import Scenario

    return Scenario.model_validate(_load_yaml(path))
