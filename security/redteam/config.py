"""Load and enforce the local-only red-team safety policy."""

from __future__ import annotations

import ipaddress
import unicodedata
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_MAX_RESPONSE_BYTES = 1_048_576


class TargetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str
    health_path: str = "/health"
    chat_path: str = "/chat"
    ledger_path: str = "/__local_test__/ledger"
    llm_telemetry_path: str = "/__local_test__/llm-telemetry"
    allowed_origins: set[str] = Field(min_length=1)
    request_timeout_seconds: float = Field(gt=0, le=60)
    max_response_bytes: int = Field(
        default=DEFAULT_MAX_RESPONSE_BYTES,
        ge=1024,
        le=5_242_880,
    )

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

    max_turns_per_scenario: int = Field(gt=0, le=50)
    max_requests_per_run: int = Field(gt=0, le=500)
    max_reference_requests_per_run: int = Field(default=1600, gt=0, le=2000)
    max_run_seconds: float = Field(gt=0, le=3600)
    agent_startup_timeout_seconds: float = Field(gt=0, le=60)
    report_finalization_timeout_seconds: float = Field(default=10, gt=0, le=60)


class AdaptiveAttackConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ollama_base_url: Literal["http://127.0.0.1:11434"] = "http://127.0.0.1:11434"
    model: str = Field(min_length=1, max_length=200)
    max_iterations_per_attack: int = Field(gt=0, le=10)
    max_generation_attempts: int = Field(gt=0, le=10)
    candidates_per_generation: int = Field(gt=1, le=5)
    duplicate_similarity_threshold: float = Field(ge=0.5, le=1.0)
    seed: int = Field(ge=0, le=2_147_483_647)
    temperature: float = Field(ge=0, le=2)
    max_output_tokens: int = Field(ge=32, le=1024)
    max_response_bytes: int = Field(
        default=DEFAULT_MAX_RESPONSE_BYTES,
        ge=1024,
        le=5_242_880,
    )

    @model_validator(mode="after")
    def output_budget_supports_candidate_count(self) -> AdaptiveAttackConfig:
        minimum_tokens = 128 * self.candidates_per_generation
        if self.max_output_tokens < minimum_tokens:
            raise ValueError(
                "max_output_tokens must provide at least 128 tokens per candidate"
            )
        return self


class JudgmentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ollama_base_url: Literal["http://127.0.0.1:11434"] = "http://127.0.0.1:11434"
    model: str = Field(min_length=1, max_length=200)
    seed: int = Field(default=0, ge=0, le=2_147_483_647)
    max_attempts_per_evaluation: int = Field(default=2, ge=1, le=3)
    max_output_tokens: int = Field(default=256, ge=64, le=512)
    max_response_bytes: int = Field(
        default=DEFAULT_MAX_RESPONSE_BYTES,
        ge=1024,
        le=5_242_880,
    )


class SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allow_remote_targets: Literal[False] = False
    required_bank_client: Literal["local"] = "local"
    required_llm_provider: Literal["ollama"] = "ollama"
    required_ollama_base_url: Literal["http://127.0.0.1:11434"] = (
        "http://127.0.0.1:11434"
    )
    required_ollama_model: str = Field(min_length=1, max_length=200)
    allowed_user_ids: set[str] = Field(min_length=1)
    redact_fields: set[str] = Field(default_factory=set)

    @field_validator("redact_fields")
    @classmethod
    def normalize_redact_fields(cls, fields: set[str]) -> set[str]:
        normalized = {
            "".join(
                character
                for character in unicodedata.normalize("NFKC", field).casefold()
                if character.isalnum()
            )
            for field in fields
        }
        if "" in normalized:
            raise ValueError("redact fields must contain letters or numbers")
        return normalized


class RedTeamConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    target: TargetConfig
    execution: ExecutionConfig
    adaptive_attack: AdaptiveAttackConfig
    judgment: JudgmentConfig
    safety: SafetyConfig

    @model_validator(mode="after")
    def require_local_target(self) -> RedTeamConfig:
        models = {
            self.adaptive_attack.model,
            self.safety.required_ollama_model,
            self.judgment.model,
        }
        if len(models) != 3:
            raise ValueError("generator, Target, and judgment models must be distinct")
        if self.safety.allow_remote_targets:
            return self

        hostname = urlparse(self.target.base_url).hostname
        if is_loopback_hostname(hostname):
            return self
        raise ValueError("remote red-team targets are disabled")


def is_loopback_hostname(hostname: str | None) -> bool:
    if hostname == "localhost":
        return True
    try:
        return bool(hostname and ipaddress.ip_address(hostname).is_loopback)
    except ValueError:
        return False


MAX_CONFIG_BYTES = 262_144
MAX_SCENARIO_BYTES = 1_048_576
MAX_YAML_NODES = 10_000
MAX_YAML_DEPTH = 20
MAX_YAML_STRING_BYTES = 1_048_576


def _validate_yaml_shape(value: object) -> None:
    stack = [(value, 0)]
    nodes = 0
    string_bytes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > MAX_YAML_NODES:
            raise ValueError("YAML contains too many values")
        if depth > MAX_YAML_DEPTH:
            raise ValueError("YAML nesting is too deep")
        if isinstance(item, str):
            string_bytes += len(item.encode("utf-8"))
            if string_bytes > MAX_YAML_STRING_BYTES:
                raise ValueError("YAML string content is too large")
        elif isinstance(item, dict):
            stack.extend((key, depth + 1) for key in item)
            stack.extend((nested, depth + 1) for nested in item.values())
        elif isinstance(item, list):
            stack.extend((nested, depth + 1) for nested in item)


def _load_yaml(path: Path, *, max_bytes: int) -> dict:
    try:
        if not path.is_file():
            raise ValueError(f"YAML path is not a regular file: {path}")
        if path.stat().st_size > max_bytes:
            raise ValueError(f"YAML file exceeds {max_bytes} bytes: {path}")
        with path.open(encoding="utf-8") as stream:
            data = yaml.safe_load(stream)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError(f"failed to load YAML file: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"expected a YAML mapping: {path}")
    _validate_yaml_shape(data)
    return data


def load_config(path: Path) -> RedTeamConfig:
    return RedTeamConfig.model_validate(_load_yaml(path, max_bytes=MAX_CONFIG_BYTES))


def load_scenario(path: Path):
    from security.redteam.models import Scenario

    return Scenario.model_validate(_load_yaml(path, max_bytes=MAX_SCENARIO_BYTES))


def load_redact_fields(path: Path) -> set[str]:
    """Best-effort extraction used before full config validation succeeds."""

    try:
        raw = _load_yaml(path, max_bytes=MAX_CONFIG_BYTES)
        safety = raw.get("safety")
        values = safety.get("redact_fields") if isinstance(safety, dict) else None
        if not isinstance(values, list):
            return set()
        normalized = set()
        for item in values:
            if not isinstance(item, str):
                continue
            try:
                normalized.update(SafetyConfig.normalize_redact_fields({item}))
            except (TypeError, ValueError):
                continue
        return normalized
    except (OSError, TypeError, ValueError):
        return set()
