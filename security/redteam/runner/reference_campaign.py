"""Aggregate executable reference cases into one bounded campaign result."""

from __future__ import annotations

import asyncio
import uuid
from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from security.redteam.models import (
    AgentResponse,
    AttackerTelemetry,
    BusinessWorkflow,
    GeneratedCandidate,
    JudgmentTelemetry,
    ModelJudgment,
    Sha256Digest,
    Verdict,
)
from security.redteam.runner.reference_cases import (
    ReferenceCase,
    ReferenceCaseEvaluation,
    ReferenceExecutionKind,
)
from security.redteam.runner.target_model import TargetModelTelemetry


class ReferenceOperationKind(StrEnum):
    START = "start"
    INPUT_RESUME = "input_resume"
    APPROVAL_RESUME = "approval_resume"
    AUTHENTICATION_RESUME = "authentication_resume"
    REJECTION_CHECK = "rejection_check"


class ReferenceExecutionStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: ReferenceOperationKind
    response: AgentResponse | None = None
    rejection_code: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def has_exactly_one_outcome(self) -> ReferenceExecutionStep:
        if (self.response is None) == (self.rejection_code is None):
            raise ValueError("reference step requires one response or rejection code")
        if self.operation == ReferenceOperationKind.REJECTION_CHECK:
            if self.rejection_code is None:
                raise ValueError("rejection step requires a rejection code")
        elif self.response is None:
            raise ValueError("accepted reference step requires a response")
        return self


class ReferenceAdaptiveAttempt(BaseModel):
    """One isolated generation, Agent execution, and evaluation cycle."""

    model_config = ConfigDict(extra="forbid")

    iteration: int = Field(ge=1, le=10)
    candidate: GeneratedCandidate | None = None
    target_model_evidence: TargetModelTelemetry | None = None
    evaluation: ReferenceCaseEvaluation
    rule_evaluation: ReferenceCaseEvaluation | None = None
    steps: list[ReferenceExecutionStep] = Field(default_factory=list, max_length=8)
    model_judgment: ModelJudgment | None = None
    judgment_agrees_with_rules: bool | None = None
    review_required: bool = False
    boundary_score: float = Field(default=0.0, ge=0.0, le=1.0)
    error_stage: str | None = Field(default=None, min_length=1, max_length=100)
    error_type: str | None = Field(default=None, min_length=1, max_length=100)
    error_reason: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def result_is_consistent(self) -> ReferenceAdaptiveAttempt:
        error_fields = (self.error_stage, self.error_type, self.error_reason)
        has_error = self.evaluation.verdict == Verdict.ERROR
        if has_error != all(value is not None for value in error_fields):
            raise ValueError("adaptive ERROR requires complete error metadata")
        if any(value is not None for value in error_fields) != all(value is not None for value in error_fields):
            raise ValueError("adaptive error metadata must be complete")
        if self.model_judgment is not None:
            uncertain = self.model_judgment.outcome.value == "uncertain"
            if uncertain != (self.judgment_agrees_with_rules is None):
                raise ValueError("adaptive judgment agreement is inconsistent")
        if self.model_judgment is not None and self.judgment_agrees_with_rules is not True and not self.review_required:
            raise ValueError("adaptive judgment disagreement requires review")
        return self


class ReferenceCampaignEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    workflow_id: BusinessWorkflow
    case_contract: ReferenceCase
    status: Literal["executed", "not_supported", "not_executed"]
    evaluation: ReferenceCaseEvaluation | None = None
    rule_evaluation: ReferenceCaseEvaluation | None = None
    candidate: GeneratedCandidate | None = None
    target_model_evidence: TargetModelTelemetry | None = None
    responses: list[AgentResponse] = Field(default_factory=list, max_length=8)
    steps: list[ReferenceExecutionStep] = Field(default_factory=list, max_length=8)
    model_judgment: ModelJudgment | None = None
    judgment_agrees_with_rules: bool | None = None
    adaptive_attempts: list[ReferenceAdaptiveAttempt] = Field(
        default_factory=list,
        max_length=10,
    )
    review_required: bool = False
    note: str | None = Field(default=None, max_length=500)
    error_stage: str | None = Field(default=None, min_length=1, max_length=100)
    error_type: str | None = Field(default=None, min_length=1, max_length=100)
    error_reason: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def result_matches_status(self) -> ReferenceCampaignEntry:
        if self.status == "executed" and self.evaluation is None:
            raise ValueError("executed reference entry requires an evaluation")
        if self.case_id != self.case_contract.id:
            raise ValueError("reference entry case id does not match its contract")
        if self.workflow_id != self.case_contract.target_workflow_id:
            raise ValueError("reference entry workflow does not match its contract")
        if (
            self.status == "executed"
            and self.evaluation is not None
            and self.evaluation.verdict != Verdict.ERROR
            and (not self.responses or not self.steps)
        ):
            raise ValueError("completed reference evaluation requires Agent execution steps")
        if self.status == "not_supported" and not self.note:
            raise ValueError("unsupported reference entry requires a note")
        if self.status == "not_supported" and (
            self.evaluation is not None
            or self.rule_evaluation is not None
            or self.candidate is not None
            or self.responses
            or self.steps
            or self.model_judgment is not None
        ):
            raise ValueError("unsupported reference entry cannot contain run results")
        if self.status == "not_executed" and (
            self.evaluation is None
            or self.evaluation.verdict != Verdict.ERROR
            or self.rule_evaluation is not None
            or self.candidate is not None
            or self.responses
            or self.steps
            or self.model_judgment is not None
        ):
            raise ValueError("not-executed reference entry requires only an ERROR result")
        if self.evaluation is not None and self.evaluation.case_id != self.case_id:
            raise ValueError("reference evaluation belongs to another case")
        if self.rule_evaluation is not None and self.rule_evaluation.case_id != self.case_id:
            raise ValueError("reference rule evaluation belongs to another case")
        error_fields = (self.error_stage, self.error_type, self.error_reason)
        if any(value is not None for value in error_fields) != all(value is not None for value in error_fields):
            raise ValueError("reference error metadata must be complete")
        has_error = self.evaluation is not None and self.evaluation.verdict == Verdict.ERROR
        if has_error != all(value is not None for value in error_fields):
            raise ValueError("reference ERROR requires error metadata")
        if self.rule_evaluation is not None and not has_error:
            raise ValueError("preserved rule evaluation requires an ERROR result")
        step_responses = [step.response for step in self.steps if step.response is not None]
        if self.responses != step_responses:
            raise ValueError("reference responses must match accepted execution steps")
        generated = self.case_contract.generation is not None
        if self.status == "executed" and self.evaluation is not None:
            if (
                generated
                and self.evaluation.verdict != Verdict.ERROR
                and (self.candidate is None or self.model_judgment is None)
            ):
                raise ValueError("generated reference entry requires generation results")
            if (
                generated
                and self.evaluation.verdict == Verdict.ERROR
                and self.error_stage == "independent_judgment"
                and (self.candidate is None or self.rule_evaluation is None or not self.responses or not self.steps)
            ):
                raise ValueError("judgment error must preserve candidate and Agent rule evidence")
            if not generated and any(
                value is not None
                for value in (
                    self.candidate,
                    self.model_judgment,
                    self.judgment_agrees_with_rules,
                )
            ):
                raise ValueError("non-generated reference entry cannot contain generation results")
            if self.model_judgment is not None:
                uncertain = self.model_judgment.outcome.value == "uncertain"
                if uncertain != (self.judgment_agrees_with_rules is None):
                    raise ValueError("judgment agreement does not match judgment outcome")
        if self.model_judgment is not None and self.evaluation is None:
            raise ValueError("model judgment requires a rule evaluation")
        if (
            self.status == "executed"
            and self.evaluation is not None
            and self.evaluation.verdict != Verdict.ERROR
            and [step.operation for step in self.steps] != _expected_operations(self.case_contract)
        ):
            raise ValueError("reference steps do not match execution kind")
        if self.model_judgment is not None and self.judgment_agrees_with_rules is not True and not self.review_required:
            raise ValueError("judgment disagreement requires review")
        if self.adaptive_attempts:
            if not generated:
                raise ValueError("only generated entries can have adaptive attempts")
            if [item.iteration for item in self.adaptive_attempts] != list(range(1, len(self.adaptive_attempts) + 1)):
                raise ValueError("adaptive attempt iterations are out of sequence")
            final = self.adaptive_attempts[-1]
            if (
                self.candidate != final.candidate
                or self.evaluation != final.evaluation
                or self.rule_evaluation != final.rule_evaluation
                or self.target_model_evidence != final.target_model_evidence
                or self.steps != final.steps
                or self.model_judgment != final.model_judgment
                or self.judgment_agrees_with_rules != final.judgment_agrees_with_rules
                or self.error_stage != final.error_stage
                or self.error_type != final.error_type
                or self.error_reason != final.error_reason
            ):
                raise ValueError("entry result must match its final adaptive attempt")
            if self.review_required != any(item.review_required for item in self.adaptive_attempts):
                raise ValueError("entry review status must include every adaptive attempt")
        return self


def _expected_operations(case: ReferenceCase) -> list[ReferenceOperationKind]:
    kind = case.execution_kind
    if kind in {ReferenceExecutionKind.SINGLE, ReferenceExecutionKind.POLICY_BLOCK}:
        return [ReferenceOperationKind.START]
    if kind == ReferenceExecutionKind.INPUT_RESUME:
        return [ReferenceOperationKind.START, ReferenceOperationKind.INPUT_RESUME]
    if kind == ReferenceExecutionKind.IDENTIFIER_VALIDATION:
        return [
            ReferenceOperationKind.START,
            ReferenceOperationKind.REJECTION_CHECK,
            ReferenceOperationKind.INPUT_RESUME,
        ]
    if kind == ReferenceExecutionKind.APPROVAL:
        return [ReferenceOperationKind.START, ReferenceOperationKind.APPROVAL_RESUME]
    if kind == ReferenceExecutionKind.APPROVAL_IDENTIFIERS:
        return [
            ReferenceOperationKind.START,
            ReferenceOperationKind.REJECTION_CHECK,
            ReferenceOperationKind.APPROVAL_RESUME,
        ]
    if kind == ReferenceExecutionKind.APPROVAL_AUTHENTICATION:
        return [
            ReferenceOperationKind.START,
            ReferenceOperationKind.APPROVAL_RESUME,
            ReferenceOperationKind.AUTHENTICATION_RESUME,
        ]
    if kind == ReferenceExecutionKind.APPROVAL_AUTHENTICATION_IDENTIFIERS:
        return [
            ReferenceOperationKind.START,
            ReferenceOperationKind.REJECTION_CHECK,
            ReferenceOperationKind.APPROVAL_RESUME,
            ReferenceOperationKind.REJECTION_CHECK,
            ReferenceOperationKind.AUTHENTICATION_RESUME,
        ]
    if kind == ReferenceExecutionKind.CHANGE_REQUESTED:
        middle = (
            [
                ReferenceOperationKind.APPROVAL_RESUME,
                ReferenceOperationKind.INPUT_RESUME,
            ]
            if case.target_workflow_id == BusinessWorkflow.SET_ACCOUNT_ALIAS
            else [ReferenceOperationKind.APPROVAL_RESUME]
        )
        return [
            ReferenceOperationKind.START,
            *middle,
            ReferenceOperationKind.APPROVAL_RESUME,
        ]
    if kind == ReferenceExecutionKind.CONVERSATION_ISOLATION:
        if case.target_workflow_id in {
            BusinessWorkflow.SET_DEFAULT_ACCOUNT,
            BusinessWorkflow.SET_ACCOUNT_ALIAS,
        }:
            one = [ReferenceOperationKind.START, ReferenceOperationKind.APPROVAL_RESUME]
        elif case.target_workflow_id == BusinessWorkflow.INTERNAL_TRANSFER:
            one = [
                ReferenceOperationKind.START,
                ReferenceOperationKind.APPROVAL_RESUME,
                ReferenceOperationKind.AUTHENTICATION_RESUME,
            ]
        else:
            one = [ReferenceOperationKind.START]
        return [*one, *one]
    raise ValueError("unsupported reference execution kind")


class ReferenceCampaignMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_source_commit: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    case_set_kind: Literal["default", "custom"]
    runner_git_commit: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{40,64}$",
    )
    runner_git_dirty: bool | None = None
    config_sha256: Sha256Digest
    case_set_sha256: Sha256Digest
    generator_model: str
    generator_model_digest: Sha256Digest
    target_model: str | None = None
    target_model_digest: Sha256Digest | None = None
    target_model_telemetry: TargetModelTelemetry | None = None
    judgment_model: str
    judgment_model_digest: Sha256Digest
    max_iterations_per_generated_case: int = Field(default=1, ge=1, le=10)
    generator_telemetry: AttackerTelemetry
    judgment_telemetry: JudgmentTelemetry

    @model_validator(mode="after")
    def telemetry_models_match_roles(self) -> ReferenceCampaignMetadata:
        if self.generator_telemetry.model != self.generator_model:
            raise ValueError("generator telemetry model does not match campaign model")

        target_values = (
            self.target_model,
            self.target_model_digest,
            self.target_model_telemetry,
        )
        if any(value is not None for value in target_values) != all(value is not None for value in target_values):
            raise ValueError("Target model metadata must be complete")

        if self.target_model_telemetry is not None and self.target_model_telemetry.model != self.target_model:
            raise ValueError("Target telemetry model does not match campaign model")

        if self.judgment_telemetry.model != self.judgment_model:
            raise ValueError("judgment telemetry model does not match campaign model")
        return self


class ReferenceCampaignResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_id: str = Field(pattern=r"^reference_[a-f0-9]{12}$")
    started_at: datetime
    completed_at: datetime
    metadata: ReferenceCampaignMetadata
    requested_cases: int = Field(ge=1, le=100)
    entries: list[ReferenceCampaignEntry] = Field(max_length=100)
    totals: dict[str, int]

    @model_validator(mode="after")
    def totals_match_entries(self) -> ReferenceCampaignResult:
        if self.completed_at < self.started_at:
            raise ValueError("reference campaign completion precedes its start")
        if len(self.entries) != self.requested_cases:
            raise ValueError("reference campaign must report every requested case")
        expected = _totals(self.entries)
        if self.totals != expected:
            raise ValueError("reference campaign totals do not match entries")
        candidate_count = sum(
            (
                sum(item.candidate is not None for item in entry.adaptive_attempts)
                if entry.adaptive_attempts
                else int(entry.candidate is not None)
            )
            for entry in self.entries
        )
        judgment_count = sum(
            (
                sum(item.model_judgment is not None for item in entry.adaptive_attempts)
                if entry.adaptive_attempts
                else int(entry.model_judgment is not None)
            )
            for entry in self.entries
        )
        if candidate_count != self.metadata.generator_telemetry.successes:
            raise ValueError("generator telemetry does not match preserved candidates")
        if judgment_count != self.metadata.judgment_telemetry.successes:
            raise ValueError("judgment telemetry does not match preserved judgments")

        target_telemetry = self.metadata.target_model_telemetry
        if target_telemetry is not None:
            target_evidence = []

            for entry in self.entries:
                if entry.adaptive_attempts:
                    target_evidence.extend(
                        item.target_model_evidence
                        for item in entry.adaptive_attempts
                        if item.target_model_evidence is not None
                    )
                elif entry.target_model_evidence is not None:
                    target_evidence.append(entry.target_model_evidence)

            if any(evidence.model != target_telemetry.model for evidence in target_evidence):
                raise ValueError("Target evidence contains another model")

            preserved = (
                sum(item.attempts for item in target_evidence),
                sum(item.successes for item in target_evidence),
                sum(item.failures for item in target_evidence),
                sum(item.fallbacks for item in target_evidence),
            )
            reported = (
                target_telemetry.attempts,
                target_telemetry.successes,
                target_telemetry.failures,
                target_telemetry.fallbacks,
            )

            if preserved != reported:
                raise ValueError("Target telemetry does not match preserved evidence")

        return self


ReferenceExecutor = Callable[[ReferenceCase], Awaitable[ReferenceCampaignEntry]]
ReferenceMetadataFactory = Callable[[], ReferenceCampaignMetadata]
ReferenceTimeoutEntryFactory = Callable[[ReferenceCase, Exception], ReferenceCampaignEntry]


class _CampaignDeadlineError(TimeoutError):
    pass


async def _execute_with_deadline(
    executor: ReferenceExecutor,
    case: ReferenceCase,
    timeout: float,
) -> ReferenceCampaignEntry:
    if timeout <= 0:
        raise _CampaignDeadlineError("reference campaign deadline exhausted")
    timeout_context = asyncio.timeout(timeout)
    try:
        async with timeout_context:
            return await executor(case)
    except TimeoutError as exc:
        if timeout_context.expired():
            raise _CampaignDeadlineError from exc
        raise


async def run_reference_campaign(
    cases: Sequence[ReferenceCase],
    executor: ReferenceExecutor,
    *,
    metadata_factory: ReferenceMetadataFactory,
    started_at: datetime | None = None,
    deadline_check: Callable[[], None] | None = None,
    remaining_seconds: Callable[[], float | None] | None = None,
    timeout_entry_factory: ReferenceTimeoutEntryFactory | None = None,
) -> ReferenceCampaignResult:
    """Run cases in stable order and preserve explicit unsupported outcomes."""

    start = started_at or datetime.now(UTC)
    if not cases:
        raise ValueError("reference campaign requires at least one case")
    if len(cases) > 100:
        raise ValueError("reference campaign supports at most 100 cases")
    case_ids = [case.id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("reference campaign case ids must be unique")
    entries = []
    ordered_cases = sorted(cases, key=lambda item: item.id)
    for index, case in enumerate(ordered_cases):
        try:
            if deadline_check is not None:
                deadline_check()
        except RuntimeError:
            entries.extend(_not_executed_entry(remaining_case) for remaining_case in ordered_cases[index:])
            break
        timeout = remaining_seconds() if remaining_seconds is not None else None
        try:
            entry = (
                await _execute_with_deadline(executor, case, timeout) if timeout is not None else await executor(case)
            )
        except _CampaignDeadlineError as exc:
            entries.append(
                timeout_entry_factory(case, exc)
                if timeout_entry_factory is not None
                else _campaign_timeout_entry(case, exc)
            )
            entries.extend(_not_executed_entry(remaining_case) for remaining_case in ordered_cases[index + 1 :])
            break
        except TimeoutError as exc:
            entries.append(_case_timeout_entry(case, exc))
            continue
        if entry.case_id != case.id or entry.workflow_id != case.target_workflow_id:
            raise ValueError("reference executor returned a result for another case")
        if entry.case_contract != case:
            raise ValueError("reference executor returned a different case contract")
        entries.append(entry)
    return ReferenceCampaignResult(
        campaign_id=f"reference_{uuid.uuid4().hex[:12]}",
        started_at=start,
        completed_at=datetime.now(UTC),
        metadata=metadata_factory(),
        requested_cases=len(ordered_cases),
        entries=entries,
        totals=_totals(entries),
    )


def _campaign_timeout_entry(
    case: ReferenceCase,
    error: Exception,
) -> ReferenceCampaignEntry:
    return ReferenceCampaignEntry(
        case_id=case.id,
        workflow_id=case.target_workflow_id,
        case_contract=case,
        status="executed",
        evaluation=ReferenceCaseEvaluation(
            case_id=case.id,
            verdict=Verdict.ERROR,
            reason="reference campaign deadline exhausted",
            evidence=[f"campaign_timeout:{type(error).__name__}"],
        ),
        review_required=True,
        error_stage="campaign_timeout",
        error_type=type(error).__name__,
        error_reason="reference campaign deadline exhausted",
    )


def _case_timeout_entry(
    case: ReferenceCase,
    error: Exception,
) -> ReferenceCampaignEntry:
    reason = "reference case execution timed out"
    return ReferenceCampaignEntry(
        case_id=case.id,
        workflow_id=case.target_workflow_id,
        case_contract=case,
        status="executed",
        evaluation=ReferenceCaseEvaluation(
            case_id=case.id,
            verdict=Verdict.ERROR,
            reason=reason,
            evidence=[f"case_timeout:{type(error).__name__}"],
        ),
        review_required=True,
        error_stage="case_execution_timeout",
        error_type=type(error).__name__,
        error_reason=reason,
    )


def _not_executed_entry(case: ReferenceCase) -> ReferenceCampaignEntry:
    reason = "reference case was not executed after campaign timeout"
    return ReferenceCampaignEntry(
        case_id=case.id,
        workflow_id=case.target_workflow_id,
        case_contract=case,
        status="not_executed",
        evaluation=ReferenceCaseEvaluation(
            case_id=case.id,
            verdict=Verdict.ERROR,
            reason=reason,
            evidence=["campaign_not_executed"],
        ),
        review_required=True,
        error_stage="campaign_not_executed",
        error_type="CampaignTimeout",
        error_reason=reason,
    )


def _totals(entries: Sequence[ReferenceCampaignEntry]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for entry in entries:
        counts[entry.status] += 1
        if entry.evaluation is not None:
            counts[entry.evaluation.verdict.value] += 1
        if entry.review_required:
            counts["review_required"] += 1
    return {
        key: counts[key]
        for key in (
            "executed",
            "not_supported",
            "not_executed",
            Verdict.PASS.value,
            Verdict.FAIL.value,
            Verdict.ERROR.value,
            "review_required",
        )
    }
