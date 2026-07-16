"""Validated contracts shared by red-team scenarios, execution, and reports."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Severity(StrEnum):
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"
    S5 = "S5"


class Verdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"


class ExecutionMode(StrEnum):
    GUARDRAIL_FALLBACK = "guardrail_fallback"
    LLM_REDTEAM = "llm_redteam"


class ExpectedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed_statuses: set[str] = Field(min_length=1)
    allowed_ui_types: set[str] = Field(default_factory=set)
    forbidden_ui_types: set[str] = Field(default_factory=set)
    forbid_sensitive_reply: bool = False
    forbidden_reply_patterns: list[str] = Field(default_factory=list)
    required_reply_patterns: list[str] = Field(default_factory=list)

    @field_validator("forbidden_reply_patterns", "required_reply_patterns")
    @classmethod
    def patterns_are_valid(cls, patterns: list[str]) -> list[str]:
        for pattern in patterns:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"invalid reply pattern: {pattern}") from exc
        return patterns


class AttackTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=2000)
    expected_response: ExpectedResponse | None = None


class LedgerExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unchanged: bool = False
    balance_deltas: dict[str, int] = Field(default_factory=dict)
    audit_log_delta: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def has_one_expectation(self) -> LedgerExpectation:
        if self.unchanged == bool(self.balance_deltas):
            raise ValueError("ledger expectation requires unchanged or balance_deltas")
        return self


class AttackCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    message: str | None = Field(default=None, min_length=1, max_length=2000)
    turns: list[AttackTurn] = Field(default_factory=list)
    expected_ledger: LedgerExpectation | None = None

    @model_validator(mode="after")
    def has_exactly_one_turn_format(self) -> AttackCase:
        if (self.message is None) == (not self.turns):
            raise ValueError("attack must define exactly one of message or turns")
        return self

    def expanded_turns(self) -> list[AttackTurn]:
        if self.message is not None:
            return [AttackTurn(message=self.message)]
        return self.turns


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    id: str = Field(pattern=r"^wf_[a-z0-9_]+$")
    name: str = Field(min_length=1)
    type: str = Field(pattern=r"^[a-z_]+$")
    goal: str = Field(min_length=1)
    severity: Severity
    preconditions: list[str] = Field(default_factory=list)
    attacks: list[AttackCase] = Field(min_length=1)
    expected_response: ExpectedResponse

    @model_validator(mode="after")
    def attack_ids_are_unique(self) -> Scenario:
        attack_ids = [attack.id for attack in self.attacks]
        if len(attack_ids) != len(set(attack_ids)):
            raise ValueError("attack ids must be unique within a scenario")
        return self


class AgentResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    reply: str
    status: str
    thread_id: str
    prompt_for: str | None = None
    ui: dict | None = None


class LedgerSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    balances: dict[str, int]
    audit_log_count: int = Field(ge=0)


class LlmTelemetry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempts: int = Field(ge=0)
    successes: int = Field(ge=0)
    failures: int = Field(ge=0)

    @model_validator(mode="after")
    def counts_are_consistent(self) -> LlmTelemetry:
        if self.attempts != self.successes + self.failures:
            raise ValueError("LLM telemetry counts are inconsistent")
        return self


class TurnResult(BaseModel):
    turn: int = Field(ge=1)
    message: str
    response: AgentResponse | None = None
    verdict: Verdict
    reason: str
    evidence: list[str] = Field(default_factory=list)


class AttackResult(BaseModel):
    attack_id: str
    verdict: Verdict
    reason: str
    evidence: list[str] = Field(default_factory=list)
    turns: list[TurnResult]


class ScenarioResult(BaseModel):
    run_id: str
    started_at: datetime
    target_origin: str
    scenario_id: str
    scenario_name: str
    severity: Severity
    execution_mode: ExecutionMode
    execution_reason: str | None = None
    llm_telemetry: LlmTelemetry | None = None
    verdict: Verdict
    results: list[AttackResult]
