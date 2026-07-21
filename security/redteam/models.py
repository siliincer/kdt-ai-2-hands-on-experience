"""Validated contracts shared by red-team scenarios, execution, and reports."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from enum import StrEnum
from math import prod
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

MAX_PROCEDURAL_VARIATION_SLOTS = 16
MAX_PROCEDURAL_CHOICES_PER_SLOT = 20
MAX_PROCEDURAL_COMBINATIONS = 4096
MAX_REGEX_PATTERNS = 50
MAX_REGEX_PATTERN_LENGTH = 200
MAX_ATTACK_TURNS = 20
MAX_SCENARIO_ATTACKS = 100
MAX_SCENARIO_PRECONDITIONS = 100

_UNSAFE_REGEX = re.compile(
    r"\\[1-9]|\\k<|\(\?[=!<]|\([^)]*[+*{][^)]*\)[+*{]|(?:\.\*){2,}|(?:\.\+){2,}"
)


def validate_bounded_regex(pattern: str) -> None:
    """Reject regex features that can make synchronous evaluation unbounded."""

    if len(pattern) > MAX_REGEX_PATTERN_LENGTH:
        raise ValueError("reply pattern is too long")
    if _UNSAFE_REGEX.search(pattern):
        raise ValueError("reply pattern uses an unsafe regex construct")
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"invalid reply pattern: {pattern}") from exc


Sha256Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
GitCommit = Annotated[str, Field(pattern=r"^[0-9a-f]{40,64}$")]


class Severity(StrEnum):
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"
    S5 = "S5"


class ScenarioCategory(StrEnum):
    POLICY_BOUNDARY = "policy_boundary"
    AUTHORIZATION_FLOW = "authorization_flow"
    DATA_CONFIDENTIALITY = "data_confidentiality"
    TOOL_GOVERNANCE = "tool_governance"
    CONVERSATION_STATE = "conversation_state"


class CoverageTag(StrEnum):
    POLICY_CONFIDENTIALITY = "policy_confidentiality"
    ROLE_CLAIM = "role_claim"
    APPROVAL_SEQUENCE = "approval_sequence"
    MULTI_TURN = "multi_turn"
    STATE_INTEGRITY = "state_integrity"
    SENSITIVE_RESPONSE = "sensitive_response"
    TOOL_EXECUTION = "tool_execution"


class BusinessWorkflow(StrEnum):
    GLOBAL_AGENT_ENTRY = "wf_global_agent_entry"
    EXTERNAL_TRANSFER = "wf_external_transfer"
    BALANCE_INQUIRY = "wf_balance_inquiry"
    ACCOUNT_LIST = "wf_account_list"
    TRANSACTION_HISTORY = "wf_transaction_history"
    PERIOD_AMOUNT_SUMMARY = "wf_period_amount_summary"
    SET_DEFAULT_ACCOUNT = "wf_set_default_account"
    SET_ACCOUNT_ALIAS = "wf_set_account_alias"
    INTERNAL_TRANSFER = "wf_internal_transfer"


class Verdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"


class JudgmentOutcome(StrEnum):
    CONSISTENT = "consistent"
    VIOLATION = "violation"
    UNCERTAIN = "uncertain"


class JudgmentCategory(StrEnum):
    STATE_TRANSITION = "state_transition"
    SENSITIVE_DATA = "sensitive_data"
    INTERNAL_POLICY = "internal_policy"
    UNAUTHORIZED_COMPLETION = "unauthorized_completion"
    OTHER = "other"


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
    SENSITIVE_DATA = "sensitive_data"
    OTHER = "other"
    UNCERTAIN = "uncertain"


class CandidateBusinessFact(StrEnum):
    RECIPIENT = "recipient"
    SOURCE_ACCOUNT = "source_account"
    AMOUNT = "amount"
    TRANSFER_ACTION = "transfer_action"
    RELATIVE_CHANGE = "relative_change"


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
    forbidden_policy_reply_patterns: list[str] = Field(
        default_factory=list, max_length=MAX_REGEX_PATTERNS
    )
    forbidden_reply_patterns: list[str] = Field(
        default_factory=list, max_length=MAX_REGEX_PATTERNS
    )
    required_reply_patterns: list[str] = Field(
        default_factory=list, max_length=MAX_REGEX_PATTERNS
    )

    @field_validator(
        "forbidden_policy_reply_patterns",
        "forbidden_reply_patterns",
        "required_reply_patterns",
    )
    @classmethod
    def patterns_are_valid(cls, patterns: list[str]) -> list[str]:
        for pattern in patterns:
            validate_bounded_regex(pattern)
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
        if any(delta == 0 for delta in self.balance_deltas.values()):
            raise ValueError("ledger balance deltas must be nonzero")
        if self.unchanged and self.audit_log_delta is None:
            self.audit_log_delta = 0
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
    target_workflow_id: BusinessWorkflow
    message: str | None = Field(default=None, min_length=1, max_length=2000)
    turns: list[AttackTurn] = Field(default_factory=list, max_length=MAX_ATTACK_TURNS)
    expected_ledger: LedgerExpectation | None = None
    adaptive: bool = False
    expected_intent_action: CandidateAction | None = None
    expected_intent_target: CandidateTarget | None = None
    candidate_template: str | None = None
    candidate_required_patterns: list[str] = Field(
        default_factory=list, max_length=MAX_REGEX_PATTERNS
    )
    variation_required_patterns: list[str] = Field(
        default_factory=list, max_length=MAX_REGEX_PATTERNS
    )
    variation_forbidden_patterns: list[str] = Field(
        default_factory=list, max_length=MAX_REGEX_PATTERNS
    )
    immutable_fact_patterns: list[str] = Field(
        default_factory=list, max_length=MAX_REGEX_PATTERNS
    )
    forbid_variation_business_facts: bool = False
    enforce_procedural_variation: bool = False
    procedural_variation_slots: list[set[str]] = Field(default_factory=list)
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
            validate_bounded_regex(pattern)
        if self.adaptive and any(
            not re.search(pattern, self.candidate_template or "", flags=re.IGNORECASE)
            for pattern in self.immutable_fact_patterns
        ):
            raise ValueError("candidate template does not contain immutable facts")
        if (
            self.forbid_variation_business_facts or self.enforce_procedural_variation
        ) and not self.procedural_variation_slots:
            raise ValueError("enforced variation requires procedural variation slots")
        if any(
            not slot or any(not choice.strip() for choice in slot)
            for slot in self.procedural_variation_slots
        ):
            raise ValueError("procedural variation slots require non-empty choices")
        if len(self.procedural_variation_slots) > MAX_PROCEDURAL_VARIATION_SLOTS:
            raise ValueError("procedural variation has too many slots")
        if any(
            len(slot) > MAX_PROCEDURAL_CHOICES_PER_SLOT
            for slot in self.procedural_variation_slots
        ):
            raise ValueError("procedural variation slot has too many choices")
        if (
            self.procedural_variation_slots
            and prod(len(slot) for slot in self.procedural_variation_slots)
            > MAX_PROCEDURAL_COMBINATIONS
        ):
            raise ValueError("procedural variation has too many combinations")
        return self

    def expanded_turns(self) -> list[AttackTurn]:
        if self.message is not None:
            return [AttackTurn(message=self.message)]
        return self.turns


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    id: str = Field(pattern=r"^wf_[a-z0-9_]+$")
    name: str = Field(min_length=1)
    type: Literal["adaptive_attack"]
    category: ScenarioCategory
    coverage: set[CoverageTag] = Field(min_length=1)
    goal: str = Field(min_length=1)
    severity: Severity
    preconditions: list[str] = Field(
        default_factory=list, max_length=MAX_SCENARIO_PRECONDITIONS
    )
    attacks: list[AttackCase] = Field(min_length=1, max_length=MAX_SCENARIO_ATTACKS)
    expected_response: ExpectedResponse

    @model_validator(mode="after")
    def attack_ids_are_unique(self) -> Scenario:
        attack_ids = [attack.id for attack in self.attacks]
        if len(attack_ids) != len(set(attack_ids)):
            raise ValueError("attack ids must be unique within a scenario")
        if not any(attack.adaptive for attack in self.attacks):
            raise ValueError("scenario requires at least one adaptive LLM case")
        return self

    @field_serializer("coverage", when_used="json")
    def serialize_coverage(self, value: set[CoverageTag]) -> list[str]:
        return sorted(tag.value for tag in value)


class AgentUiEnvelope(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)

    type: str = Field(min_length=1, max_length=100)


class WorkflowWebhookEvidence(BaseModel):
    """Bounded metadata from one reference-runtime webhook request."""

    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(min_length=1, max_length=100)
    step_id: str | None = Field(default=None, max_length=200)


class WorkflowToolRequestEvidence(BaseModel):
    """Bounded request metadata and an ephemeral keyed payload digest."""

    model_config = ConfigDict(extra="forbid")

    method: str = Field(pattern=r"^(GET|POST|PUT|PATCH|DELETE)$")
    path: str = Field(min_length=1, max_length=500)
    query_keys: list[str] = Field(default_factory=list, max_length=100)
    payload_digest: Sha256Digest | None = None


class WorkflowTraceEvidence(BaseModel):
    """One workflow step recorded by the Agent checkpoint."""

    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1, max_length=200)
    route_key: str | None = Field(default=None, max_length=200)


class WorkflowExecutionEvidence(BaseModel):
    """Local reference-runtime evidence; never supplied by an HTTP 202 response."""

    model_config = ConfigDict(extra="forbid")

    observed_workflow_id: BusinessWorkflow
    runtime_status: str = Field(min_length=1, max_length=100)
    state_status: str = Field(min_length=1, max_length=100)
    request_ids: list[str] = Field(default_factory=list, max_length=100)
    execution_context_ids: list[str] = Field(default_factory=list, max_length=100)
    chat_session_ids: list[str] = Field(default_factory=list, max_length=100)
    tool_request_paths: list[str] = Field(default_factory=list, max_length=100)
    tool_requests: list[WorkflowToolRequestEvidence] = Field(
        default_factory=list,
        max_length=100,
    )
    contract_tool_ids: list[str] = Field(default_factory=list, max_length=100)
    webhooks: list[WorkflowWebhookEvidence] = Field(
        default_factory=list,
        max_length=100,
    )
    pending_identifiers: dict[str, str] = Field(
        default_factory=dict,
        max_length=20,
    )
    trace: list[WorkflowTraceEvidence] = Field(default_factory=list, max_length=200)
    state_contains_sensitive_data: bool | None = None
    webhook_payloads_contain_sensitive_data: bool | None = None
    tool_arguments_valid: bool | None = None
    backend_exchanges_valid: bool | None = None
    state_projection_digest: Sha256Digest | None = None
    state_projection_values: dict[str, list[Sha256Digest]] = Field(
        default_factory=dict,
        max_length=100,
    )
    webhook_payload_digest: Sha256Digest | None = None
    backend_exchange_digest: Sha256Digest | None = None

    @field_validator("tool_request_paths")
    @classmethod
    def tool_paths_are_local_absolute_paths(cls, paths: list[str]) -> list[str]:
        if any(
            not path.startswith("/") or path.startswith("//") or len(path) > 500
            for path in paths
        ):
            raise ValueError("tool request paths must be bounded absolute paths")
        return paths


class AgentResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    reply: str = Field(max_length=20_000)
    status: str = Field(min_length=1, max_length=100)
    thread_id: str = Field(min_length=1, max_length=200)
    prompt_for: str | None = Field(default=None, max_length=200)
    ui: AgentUiEnvelope | None = None
    execution_evidence: WorkflowExecutionEvidence | None = None

    @model_validator(mode="before")
    @classmethod
    def response_shape_is_bounded(cls, value: object) -> object:
        stack = [(value, 0)]
        nodes = 0
        while stack:
            item, depth = stack.pop()
            nodes += 1
            if nodes > 2000:
                raise ValueError("agent response contains too many values")
            if depth > 10:
                raise ValueError("agent response nesting is too deep")
            if isinstance(item, str) and len(item) > 20_000:
                raise ValueError("agent response string is too long")
            if isinstance(item, Mapping):
                if len(item) > 200:
                    raise ValueError("agent response mapping is too large")
                for key, nested in item.items():
                    if isinstance(key, str) and len(key) > 200:
                        raise ValueError("agent response key is too long")
                    stack.append((nested, depth + 1))
            elif isinstance(item, Sequence) and not isinstance(
                item, (str, bytes, bytearray)
            ):
                if len(item) > 200:
                    raise ValueError("agent response sequence is too large")
                stack.extend((nested, depth + 1) for nested in item)
        return value


class AuditEventSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(min_length=1)
    workflow_id: str | None = None
    tool_id: str | None = None
    result_digest: Sha256Digest


class LedgerSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    balances: dict[str, int]
    audit_log_count: int = Field(ge=0)
    account_state_digests: dict[str, Sha256Digest]
    collection_state_digests: dict[str, Sha256Digest]
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
    policy_marker_injections: int = Field(ge=0)

    @model_validator(mode="after")
    def counts_are_consistent(self) -> LlmTelemetry:
        if self.attempts != self.successes + self.failures:
            raise ValueError("LLM telemetry counts are inconsistent")
        if self.policy_marker_injections > self.attempts:
            raise ValueError("policy marker injections exceed LLM attempts")
        return self


class AttackerTelemetry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    classifier_model: str | None = None
    requests: int = Field(default=0, ge=0)
    attempts: int = Field(ge=0)
    successes: int = Field(ge=0)
    failures: int = Field(ge=0)
    rejected_out_of_scope: int = Field(ge=0)
    rejected_duplicates: int = Field(default=0, ge=0)
    rejection_reasons: dict[str, int] = Field(default_factory=dict)
    rejected_business_fact_mentions: dict[str, int] = Field(default_factory=dict)
    rejected_intents: dict[str, int] = Field(default_factory=dict)
    response_done_reasons: dict[str, int] = Field(default_factory=dict)
    max_response_chars: int = Field(default=0, ge=0)

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
    business_fact_mentions: set[CandidateBusinessFact]

    @field_serializer("business_fact_mentions", when_used="json")
    def serialize_business_facts(
        self,
        value: set[CandidateBusinessFact],
    ) -> list[str]:
        return sorted(fact.value for fact in value)


class GenerationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    style: str = Field(min_length=1, max_length=100)
    focus: str = Field(min_length=1, max_length=500)
    seed: int = Field(ge=0)
    candidate_count: int = Field(gt=1, le=5)


class ModelJudgment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    outcome: JudgmentOutcome
    categories: set[JudgmentCategory]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_fields: set[Literal["status", "reply", "prompt_for", "ui_type"]]

    @field_serializer("categories", "evidence_fields", when_used="json")
    def serialize_sets(self, value: set) -> list:
        return sorted(
            item.value if isinstance(item, StrEnum) else item for item in value
        )

    @model_validator(mode="after")
    def violation_requires_response_evidence(self) -> ModelJudgment:
        if self.outcome == JudgmentOutcome.VIOLATION and (
            not self.categories or not self.evidence_fields
        ):
            raise ValueError(
                "violation judgment requires a category and response evidence"
            )
        return self


class JudgmentTelemetry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    attempts: int = Field(ge=0)
    successes: int = Field(ge=0)
    failures: int = Field(ge=0)
    agreements: int = Field(ge=0)
    disagreements: int = Field(ge=0)
    uncertain: int = Field(ge=0)

    @model_validator(mode="after")
    def counts_are_consistent(self) -> JudgmentTelemetry:
        if self.attempts != self.successes + self.failures:
            raise ValueError("judgment attempt counts are inconsistent")
        if self.successes != self.agreements + self.disagreements + self.uncertain:
            raise ValueError("judgment result counts are inconsistent")
        return self


class TurnResult(BaseModel):
    turn: int = Field(ge=1)
    message: str
    response: AgentResponse | None = None
    verdict: Verdict
    boundary_score: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str
    evidence: list[str] = Field(default_factory=list)
    model_judgment: ModelJudgment | None = None
    judgment_agrees_with_rules: bool | None = None


class AttackResult(BaseModel):
    attack_id: str
    target_workflow_id: BusinessWorkflow = BusinessWorkflow.GLOBAL_AGENT_ENTRY
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
    generation_business_fact_mentions: set[CandidateBusinessFact] = Field(
        default_factory=set
    )
    verdict: Verdict
    boundary_score: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str
    evidence: list[str] = Field(default_factory=list)
    execution_error: str | None = None
    turns: list[TurnResult]

    @field_serializer("generation_business_fact_mentions", when_used="json")
    def serialize_generation_business_facts(
        self,
        value: set[CandidateBusinessFact],
    ) -> list[str]:
        return sorted(fact.value for fact in value)


class AdaptiveLoopSummary(BaseModel):
    attack_id: str
    iterations_completed: int = Field(ge=1)
    best_score: float = Field(default=0.0, ge=0.0, le=1.0)
    termination: LoopTermination


class ExecutionErrorReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_type: Literal["execution_error"] = "execution_error"
    run_id: str
    started_at: datetime
    completed_at: datetime
    duration_seconds: float = Field(ge=0.0)
    scenario_name: str
    stage: str
    error_type: str
    error_message: str
    verdict: Literal["ERROR"] = "ERROR"


class ReproducibilityMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generator_model: str
    generator_model_digest: Sha256Digest
    target_model: str
    target_model_digest: Sha256Digest
    judgment_model: str
    judgment_model_digest: Sha256Digest
    seed: int = Field(ge=0)
    config_sha256: Sha256Digest
    scenario_sha256: Sha256Digest
    git_commit: GitCommit | None = None
    git_dirty: bool | None = None


class ScenarioResult(BaseModel):
    run_id: str
    started_at: datetime
    completed_at: datetime
    duration_seconds: float = Field(ge=0.0)
    target_origin: str
    config_version: Literal[1]
    scenario_version: Literal[1]
    scenario_type: Literal["adaptive_attack"]
    scenario_category: ScenarioCategory
    scenario_coverage: set[CoverageTag]
    scenario_id: str
    scenario_name: str
    severity: Severity
    execution_mode: Literal["adaptive_llm"] = "adaptive_llm"
    execution_reason: str | None = None
    reproducibility: ReproducibilityMetadata | None = None
    review_required: bool = False
    llm_telemetry: LlmTelemetry | None = None
    attacker_telemetry: AttackerTelemetry | None = None
    judgment_telemetry: JudgmentTelemetry | None = None
    loop_summaries: list[AdaptiveLoopSummary] = Field(default_factory=list)
    workflow_verdicts: dict[BusinessWorkflow, Verdict] = Field(default_factory=dict)
    verdict: Verdict
    results: list[AttackResult]

    @field_serializer("scenario_coverage", when_used="json")
    def serialize_scenario_coverage(self, value: set[CoverageTag]) -> list[str]:
        return sorted(tag.value for tag in value)


class ComparisonRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_name: str
    generator_model: str
    target_model: str
    judgment_model: str
    seed: int = Field(ge=0)
    verdict: Verdict
    duration_seconds: float = Field(ge=0.0)
    report_json: str
    report_markdown: str
    result_counts: dict[Verdict, int]
    generator_requests: int = Field(ge=0)
    generator_attempts: int = Field(ge=0)
    generator_successes: int = Field(ge=0)
    generator_rejections: int = Field(ge=0)
    generator_failures: int = Field(ge=0)
    target_attempts: int = Field(ge=0)
    target_failures: int = Field(ge=0)
    judgment_attempts: int = Field(ge=0)
    judgment_failures: int = Field(ge=0)
    judgment_disagreements: int = Field(ge=0)
    judgment_uncertain: int = Field(ge=0)
    review_required: bool

    @model_validator(mode="after")
    def metric_counts_are_consistent(self) -> ComparisonRun:
        if self.generator_attempts != (
            self.generator_successes
            + self.generator_rejections
            + self.generator_failures
        ):
            raise ValueError("comparison generator counts are inconsistent")
        if self.target_failures > self.target_attempts:
            raise ValueError("comparison Target failures exceed attempts")
        if self.judgment_failures > self.judgment_attempts:
            raise ValueError("comparison judgment failures exceed attempts")
        if (
            self.judgment_failures
            + self.judgment_disagreements
            + self.judgment_uncertain
            > self.judgment_attempts
        ):
            raise ValueError("comparison judgment result counts exceed attempts")
        return self


class ModelRoleSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["generator", "target", "judgment"]
    model: str
    total_runs: int = Field(ge=1)
    run_verdict_counts: dict[Verdict, int]
    average_duration_seconds: float = Field(ge=0.0)
    generator_success_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    generator_rejection_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    generator_failure_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    target_contract_pass_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    target_contract_fail_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    target_contract_error_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    target_llm_failure_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    judgment_agreement_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    judgment_disagreement_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    judgment_uncertain_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    judgment_failure_rate: float | None = Field(default=None, ge=0.0, le=1.0)


class ModelCombinationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_name: str
    generator_model: str
    target_model: str
    judgment_model: str
    seeds: list[int] = Field(min_length=1)
    total_runs: int = Field(ge=1)
    verdict_counts: dict[Verdict, int]
    stable_verdict: Verdict | None = None
    verdict_consistency_rate: float = Field(ge=0.0, le=1.0)
    review_required_rate: float = Field(ge=0.0, le=1.0)
    average_duration_seconds: float = Field(ge=0.0)
    generator_success_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    target_contract_pass_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    judgment_agreement_rate: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def summary_matches_seed_runs(self) -> ModelCombinationSummary:
        if self.seeds != sorted(set(self.seeds)):
            raise ValueError("combination seeds must be sorted and unique")
        if self.total_runs != len(self.seeds):
            raise ValueError("combination run count must match seeds")
        if sum(self.verdict_counts.values()) != self.total_runs:
            raise ValueError("combination verdict counts must match runs")
        observed = [
            verdict for verdict, count in self.verdict_counts.items() if count > 0
        ]
        expected_stable = observed[0] if len(observed) == 1 else None
        if self.stable_verdict != expected_stable:
            raise ValueError("combination stable verdict is inconsistent")
        expected_consistency = max(self.verdict_counts.values()) / self.total_runs
        if abs(self.verdict_consistency_rate - expected_consistency) > 1e-12:
            raise ValueError("combination consistency rate is inconsistent")
        return self


class ComparisonReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_type: Literal["model_comparison"] = "model_comparison"
    comparison_id: str
    started_at: datetime
    completed_at: datetime
    duration_seconds: float = Field(ge=0.0)
    requested_scenario: str
    total_runs: int = Field(ge=1, le=100)
    verdict_counts: dict[Verdict, int]
    runs: list[ComparisonRun] = Field(min_length=1, max_length=100)
    model_summaries: list[ModelRoleSummary] = Field(min_length=3, max_length=300)
    combination_summaries: list[ModelCombinationSummary] = Field(
        min_length=1,
        max_length=100,
    )

    @model_validator(mode="after")
    def counts_match_runs(self) -> ComparisonReport:
        expected = {verdict: 0 for verdict in Verdict}
        for run in self.runs:
            expected[run.verdict] += 1
        if self.total_runs != len(self.runs) or self.verdict_counts != expected:
            raise ValueError("comparison summary counts do not match runs")
        run_keys = {
            (
                run.scenario_name,
                run.generator_model,
                run.target_model,
                run.judgment_model,
            )
            for run in self.runs
        }
        summary_keys = {
            (
                summary.scenario_name,
                summary.generator_model,
                summary.target_model,
                summary.judgment_model,
            )
            for summary in self.combination_summaries
        }
        if run_keys != summary_keys:
            raise ValueError("comparison combination summaries do not match runs")
        if sum(summary.total_runs for summary in self.combination_summaries) != len(
            self.runs
        ):
            raise ValueError("comparison combination run counts do not match runs")
        return self
