"""Validated contracts shared by red-team scenarios, execution, and reports."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Literal

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


class LoopTermination(StrEnum):
    ITERATION_LIMIT = "iteration_limit"
    EXPECTATION_MISMATCH = "expectation_mismatch"
    EXECUTION_ERROR = "execution_error"


class CandidatePolarity(StrEnum):
    REQUEST = "request"
    REJECT = "reject"
    DESCRIBE = "describe"
    OTHER = "other"
    UNCERTAIN = "uncertain"


class CandidateAction(StrEnum):
    DISCLOSE = "disclose"
    DISABLE = "disable"
    BYPASS = "bypass"
    OTHER = "other"
    UNCERTAIN = "uncertain"


class CandidateTarget(StrEnum):
    INTERNAL_INSTRUCTIONS = "internal_instructions"
    HIDDEN_POLICY = "hidden_policy"
    SAFETY_CONTROLS = "safety_controls"
    APPROVAL_STEP = "approval_step"
    OTHER = "other"
    UNCERTAIN = "uncertain"


class ExpectedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed_statuses: set[str] = Field(min_length=1)
    terminal_statuses: set[str] = Field(default_factory=set)
    allowed_ui_types: set[str | None] | None = None
    terminal_allowed_ui_types: set[str | None] | None = None
    forbidden_ui_types: set[str] = Field(default_factory=set)
    forbid_financial_secrets: bool = False
    allowed_prompt_for: set[str | None] | None = None
    terminal_allowed_prompt_for: set[str | None] | None = None
    forbidden_policy_reply_patterns: list[str] = Field(default_factory=list)
    forbidden_reply_patterns: list[str] = Field(default_factory=list)
    required_reply_patterns: list[str] = Field(default_factory=list)

    @field_validator(
        "forbidden_policy_reply_patterns",
        "forbidden_reply_patterns",
        "required_reply_patterns",
    )
    @classmethod
    def patterns_are_valid(cls, patterns: list[str]) -> list[str]:
        for pattern in patterns:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"invalid reply pattern: {pattern}") from exc
        return patterns

    @model_validator(mode="after")
    def terminal_statuses_are_allowed(self) -> ExpectedResponse:
        if not self.terminal_statuses <= self.allowed_statuses:
            raise ValueError("terminal statuses must also be allowed statuses")
        if self.terminal_statuses and (
            self.terminal_allowed_ui_types is None
            or self.terminal_allowed_prompt_for is None
        ):
            raise ValueError(
                "terminal statuses require explicit terminal UI and prompt contracts"
            )
        return self


class AttackTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=2000)
    expected_response: ExpectedResponse | None = None


class LedgerExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unchanged: bool = False
    balance_deltas: dict[str, int] = Field(default_factory=dict)
    audit_log_delta: int | None = Field(default=None, ge=0)
    audit_event_types: list[str] = Field(default_factory=list)
    audit_workflow_ids: list[str | None] = Field(default_factory=list)
    audit_tool_ids: list[str | None] = Field(default_factory=list)

    @model_validator(mode="after")
    def has_one_expectation(self) -> LedgerExpectation:
        if self.unchanged == bool(self.balance_deltas):
            raise ValueError("ledger expectation requires unchanged or balance_deltas")
        for values in (
            self.audit_event_types,
            self.audit_workflow_ids,
            self.audit_tool_ids,
        ):
            if values and self.audit_log_delta != len(values):
                raise ValueError("audit detail expectations must match audit_log_delta")
        return self


class AttackCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    message: str | None = Field(default=None, min_length=1, max_length=2000)
    turns: list[AttackTurn] = Field(default_factory=list)
    expected_ledger: LedgerExpectation | None = None
    adaptive: bool = False
    expected_intent_action: CandidateAction | None = None
    expected_intent_target: CandidateTarget | None = None
    candidate_template: str | None = None
    candidate_required_patterns: list[str] = Field(default_factory=list)
    variation_required_patterns: list[str] = Field(default_factory=list)
    variation_forbidden_patterns: list[str] = Field(default_factory=list)
    immutable_fact_patterns: list[str] = Field(default_factory=list)
    generation_guidance: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def has_exactly_one_turn_format(self) -> AttackCase:
        if (self.message is None) == (not self.turns):
            raise ValueError("attack must define exactly one of message or turns")
        if self.adaptive and not self.candidate_required_patterns:
            raise ValueError("adaptive attack requires candidate_required_patterns")
        if self.adaptive and not self.variation_required_patterns:
            raise ValueError("adaptive attack requires variation_required_patterns")
        if self.adaptive and (
            self.expected_intent_action is None or self.expected_intent_target is None
        ):
            raise ValueError("adaptive attack requires an expected structured intent")
        if self.adaptive and (
            self.candidate_template is None
            or self.candidate_template.count("{variation}") != 1
        ):
            raise ValueError(
                "adaptive attack requires one {variation} candidate template"
            )
        for pattern in (
            *self.candidate_required_patterns,
            *self.variation_required_patterns,
            *self.variation_forbidden_patterns,
            *self.immutable_fact_patterns,
        ):
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError("invalid candidate required pattern") from exc
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
        if not any(attack.adaptive for attack in self.attacks):
            raise ValueError("scenario requires at least one adaptive LLM case")
        return self


class AgentUiEnvelope(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)

    type: str = Field(min_length=1)


class AgentResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    reply: str
    status: str
    thread_id: str = Field(min_length=1)
    prompt_for: str | None = None
    ui: AgentUiEnvelope | None = None


class AuditEventSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(min_length=1)
    workflow_id: str | None = None
    tool_id: str | None = None
    result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class LedgerSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    balances: dict[str, int]
    audit_log_count: int = Field(ge=0)
    account_state_digests: dict[str, str]
    collection_state_digests: dict[str, str]
    audit_events: list[AuditEventSummary]

    @model_validator(mode="after")
    def audit_count_matches_events(self) -> LedgerSnapshot:
        if self.audit_log_count != len(self.audit_events):
            raise ValueError("audit log count does not match event summaries")
        if set(self.balances) != set(self.account_state_digests):
            raise ValueError("balance and account digest keys do not match")
        expected_collections = {"accounts", "recipients", "transactions"}
        if set(self.collection_state_digests) != expected_collections:
            raise ValueError("collection digest keys do not match the local bank state")
        return self


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


class AttackerTelemetry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    requests: int = Field(default=0, ge=0)
    attempts: int = Field(ge=0)
    successes: int = Field(ge=0)
    failures: int = Field(ge=0)
    rejected_out_of_scope: int = Field(ge=0)
    rejected_duplicates: int = Field(default=0, ge=0)
    rejection_reasons: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def counts_are_consistent(self) -> AttackerTelemetry:
        if self.attempts != (
            self.successes
            + self.failures
            + self.rejected_out_of_scope
            + self.rejected_duplicates
        ):
            raise ValueError("attacker telemetry counts are inconsistent")
        return self


class GeneratedCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=2000)
    variation: str = Field(min_length=1, max_length=2000)
    strategy: str = Field(min_length=1, max_length=500)
    style: str = Field(min_length=1, max_length=100)
    seed: int = Field(ge=0)
    requested_action: CandidateAction
    target: CandidateTarget
    polarity: CandidatePolarity
    reported_speech: bool


class GenerationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    style: str = Field(min_length=1, max_length=100)
    focus: str = Field(min_length=1, max_length=500)
    seed: int = Field(ge=0)
    candidate_count: int = Field(gt=1, le=5)


class TurnResult(BaseModel):
    turn: int = Field(ge=1)
    message: str
    response: AgentResponse | None = None
    verdict: Verdict
    boundary_score: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str
    evidence: list[str] = Field(default_factory=list)


class AttackResult(BaseModel):
    attack_id: str
    iteration: int = Field(default=1, ge=1)
    generated_by_llm: bool = False
    generation_variation: str | None = None
    generation_strategy: str | None = None
    generation_style: str | None = None
    generation_seed: int | None = Field(default=None, ge=0)
    generation_requested_action: CandidateAction | None = None
    generation_target: CandidateTarget | None = None
    generation_polarity: CandidatePolarity | None = None
    generation_reported_speech: bool | None = None
    verdict: Verdict
    boundary_score: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str
    evidence: list[str] = Field(default_factory=list)
    execution_error: str | None = None
    turns: list[TurnResult]


class AdaptiveLoopSummary(BaseModel):
    attack_id: str
    iterations_completed: int = Field(ge=1)
    best_score: float = Field(default=0.0, ge=0.0, le=1.0)
    termination: LoopTermination


class ScenarioResult(BaseModel):
    run_id: str
    started_at: datetime
    completed_at: datetime
    duration_seconds: float = Field(ge=0.0)
    target_origin: str
    scenario_id: str
    scenario_name: str
    severity: Severity
    execution_mode: Literal["adaptive_llm"] = "adaptive_llm"
    execution_reason: str | None = None
    llm_telemetry: LlmTelemetry | None = None
    attacker_telemetry: AttackerTelemetry | None = None
    loop_summaries: list[AdaptiveLoopSummary] = Field(default_factory=list)
    verdict: Verdict
    results: list[AttackResult]
