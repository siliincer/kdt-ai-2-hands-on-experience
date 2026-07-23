from __future__ import annotations

import asyncio
import importlib.util
import warnings
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

import security.redteam.runner.agent_reference as agent_reference_module
from security.redteam.config import load_scenario
from security.redteam.models import (
    AgentResponse,
    AttackCase,
    AttackerTelemetry,
    AttackResult,
    CandidatePolarity,
    ExpectedResponse,
    GeneratedCandidate,
    JudgmentOutcome,
    JudgmentTelemetry,
    ModelJudgment,
    Scenario,
    Verdict,
)
from security.redteam.runner.agent_reference import AgentReferenceExecutor
from security.redteam.runner.cli import _canonical_sha256
from security.redteam.runner.client import RequestBudget, RequestBudgetError
from security.redteam.runner.reference_campaign import (
    ReferenceCampaignMetadata,
    ReferenceOperationKind,
    run_reference_campaign,
)
from security.redteam.runner.reference_cases import (
    ReferenceCase,
    ReferenceCaseEvaluation,
    evaluate_reference_steps,
    load_reference_case,
)

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(
    any(
        importlib.util.find_spec(module) is None
        for module in ("agent.clients", "agent.testing", "agent.workflow_contracts")
    ),
    reason="reference Agent integration source is not present in this checkout",
)


class _Generator:
    def __init__(self) -> None:
        self.successes = 0

    def generate(
        self,
        scenario: Scenario,
        attack: AttackCase,
        history: Sequence[AttackResult],
    ) -> GeneratedCandidate:
        del scenario, history
        self.successes += 1
        assert attack.message is not None
        assert attack.expected_intent_action is not None
        assert attack.expected_intent_target is not None
        return GeneratedCandidate(
            message=attack.message,
            variation=attack.message,
            strategy="deterministic Agent integration fixture",
            style="fixture",
            seed=1,
            requested_action=attack.expected_intent_action,
            target=attack.expected_intent_target,
            polarity=CandidatePolarity.REQUEST,
            reported_speech=False,
            business_fact_mentions=set(),
        )

    def telemetry(self) -> AttackerTelemetry:
        return AttackerTelemetry(
            model="integration-generator",
            attempts=self.successes,
            successes=self.successes,
            failures=0,
            rejected_out_of_scope=0,
        )


class _Judge:
    def __init__(self) -> None:
        self.successes = 0

    def evaluate(
        self,
        scenario: Scenario,
        expected: ExpectedResponse,
        message: str,
        response: AgentResponse,
        rule_verdict: Verdict,
    ) -> ModelJudgment:
        del scenario, expected, message, response
        self.successes += 1
        return ModelJudgment(
            model="integration-judge",
            outcome=(
                JudgmentOutcome.VIOLATION
                if rule_verdict == Verdict.FAIL
                else JudgmentOutcome.CONSISTENT
            ),
            categories=set(),
            confidence=1,
            evidence_fields={"status"},
        )

    def telemetry(self) -> JudgmentTelemetry:
        return JudgmentTelemetry(
            model="integration-judge",
            attempts=self.successes,
            successes=self.successes,
            failures=0,
            agreements=self.successes,
            disagreements=0,
            uncertain=0,
        )


def _metadata(
    cases: list,
    generator: _Generator,
    judge: _Judge,
    agent_source_commit: str,
) -> ReferenceCampaignMetadata:
    return ReferenceCampaignMetadata(
        agent_source_commit=agent_source_commit,
        case_set_kind="default",
        runner_git_commit=None,
        runner_git_dirty=None,
        config_sha256="a" * 64,
        case_set_sha256=_canonical_sha256(cases),
        generator_model="integration-generator",
        generator_model_digest="b" * 64,
        judgment_model="integration-judge",
        judgment_model_digest="c" * 64,
        generator_telemetry=generator.telemetry(),
        judgment_telemetry=judge.telemetry(),
    )


@pytest.mark.asyncio
async def test_all_reference_cases_have_reproducible_agent_outcomes() -> None:
    cases = [
        load_reference_case(path)
        for path in sorted((ROOT / "reference_cases").glob("*.yaml"))
    ]
    scenarios = {
        name: load_scenario(ROOT / "scenarios" / f"{name}.yaml")
        for name in ("prompt_injection", "tool_governance", "data_confidentiality")
    }
    generator = _Generator()
    judge = _Judge()
    executor = AgentReferenceExecutor(
        generator,
        judge,
        scenarios,
        {"account_number", "authorization", "token"},
    )
    assert executor.agent_source_dirty is False
    assert executor.resolve_source_commit(executor.agent_source_commit[:7]) == (
        executor.agent_source_commit
    )
    with pytest.raises(ValueError, match="imported checkout"):
        executor.resolve_source_commit("f" * 40)

    result = await run_reference_campaign(
        cases,
        executor,
        metadata_factory=lambda: _metadata(
            cases,
            generator,
            judge,
            executor.agent_source_commit,
        ),
    )

    failures = [
        (entry.case_id, entry.evaluation)
        for entry in result.entries
        if entry.evaluation is not None and entry.evaluation.verdict != Verdict.PASS
    ]
    assert failures == []
    assert result.totals == {
        "executed": 51,
        "not_supported": 0,
        "not_executed": 0,
        "PASS": 51,
        "FAIL": 0,
        "ERROR": 0,
        "review_required": 0,
    }
    manifest = yaml.safe_load(
        (ROOT / "reference_evidence_manifest.yaml").read_text(encoding="utf-8")
    )
    assert manifest["agent_source_commit"] == executor.agent_source_commit
    assert result.metadata.agent_source_commit == manifest["agent_source_commit"]
    assert result.metadata.case_set_sha256 == manifest["case_set_sha256"]
    assert [entry.case_id for entry in result.entries] == manifest["case_ids"]
    by_id = {entry.case_id: entry for entry in result.entries}
    assert [
        step.operation for step in by_id["balance_multi_step_identifiers"].steps
    ] == [
        ReferenceOperationKind.START,
        ReferenceOperationKind.REJECTION_CHECK,
        ReferenceOperationKind.INPUT_RESUME,
    ]
    assert [
        step.rejection_code
        for step in by_id["internal_transfer_lifecycle"].steps
        if step.rejection_code is not None
    ] == ["PENDING_IDENTIFIER_MISMATCH", "PENDING_IDENTIFIER_MISMATCH"]
    assert len(by_id["internal_transfer_lifecycle"].responses) == 3


@pytest.mark.asyncio
async def test_reference_execution_semantics_do_not_depend_on_case_id() -> None:
    original = load_reference_case(
        ROOT / "reference_cases" / "account_list_generated_instruction_case.yaml"
    )
    renamed = original.model_copy(update={"id": "renamed_generated_case"})
    executor = AgentReferenceExecutor(
        _Generator(),
        _Judge(),
        {
            name: load_scenario(ROOT / "scenarios" / f"{name}.yaml")
            for name in (
                "prompt_injection",
                "tool_governance",
                "data_confidentiality",
            )
        },
        {"token"},
    )

    entry = await executor(renamed)

    assert entry.case_contract == renamed
    assert entry.evaluation is not None
    assert entry.evaluation.verdict == Verdict.PASS


@pytest.mark.asyncio
async def test_generated_reference_case_adapts_from_previous_agent_results() -> None:
    class HistoryGenerator(_Generator):
        def __init__(self) -> None:
            super().__init__()
            self.history_lengths: list[int] = []

        def generate(
            self,
            scenario: Scenario,
            attack: AttackCase,
            history: Sequence[AttackResult],
        ) -> GeneratedCandidate:
            self.history_lengths.append(len(history))
            candidate = super().generate(scenario, attack, history)
            return candidate.model_copy(
                update={
                    "variation": f"adaptive variation {len(history) + 1}",
                    "strategy": f"adaptive strategy {len(history) + 1}",
                    "style": f"adaptive style {len(history) + 1}",
                    "seed": len(history) + 1,
                }
            )

    generator = HistoryGenerator()
    judge = _Judge()
    executor = AgentReferenceExecutor(
        generator,
        judge,
        {
            name: load_scenario(ROOT / "scenarios" / f"{name}.yaml")
            for name in (
                "prompt_injection",
                "tool_governance",
                "data_confidentiality",
            )
        },
        {"token"},
        max_iterations_per_generated_case=3,
    )
    case = load_reference_case(
        ROOT / "reference_cases" / "account_list_generated_instruction_case.yaml"
    )

    entry = await executor(case)

    assert generator.history_lengths == [0, 1, 2]
    assert generator.successes == 3
    assert judge.successes == 3
    assert len(entry.adaptive_attempts) == 3
    assert [attempt.iteration for attempt in entry.adaptive_attempts] == [1, 2, 3]
    assert [
        attempt.candidate.strategy
        for attempt in entry.adaptive_attempts
        if attempt.candidate is not None
    ] == [
        "adaptive strategy 1",
        "adaptive strategy 2",
        "adaptive strategy 3",
    ]
    assert entry.candidate == entry.adaptive_attempts[-1].candidate
    assert entry.evaluation == entry.adaptive_attempts[-1].evaluation


@pytest.mark.asyncio
async def test_agent_reference_isolates_one_generator_failure() -> None:
    class FailingGenerator(_Generator):
        def generate(
            self,
            scenario: Scenario,
            attack: AttackCase,
            history: Sequence[AttackResult],
        ) -> GeneratedCandidate:
            del scenario, attack, history
            raise ValueError("synthetic model output")

    executor = AgentReferenceExecutor(
        FailingGenerator(),
        _Judge(),
        {
            name: load_scenario(ROOT / "scenarios" / f"{name}.yaml")
            for name in (
                "prompt_injection",
                "tool_governance",
                "data_confidentiality",
            )
        },
        {"token"},
    )
    case = load_reference_case(
        ROOT / "reference_cases" / "account_list_generated_instruction_case.yaml"
    )

    entry = await executor(case)

    assert entry.evaluation is not None
    assert entry.evaluation.verdict == Verdict.ERROR
    assert entry.evaluation.evidence == ["input_generation_error:ValueError"]
    assert entry.error_stage == "input_generation"
    assert entry.review_required is True


@pytest.mark.asyncio
async def test_agent_reference_preserves_evidence_when_judgment_fails() -> None:
    class FailingJudge(_Judge):
        def evaluate(self, *args, **kwargs) -> ModelJudgment:
            del args, kwargs
            raise ValueError("synthetic judgment output")

    case = load_reference_case(
        ROOT / "reference_cases" / "account_list_generated_instruction_case.yaml"
    )
    executor = AgentReferenceExecutor(
        _Generator(),
        FailingJudge(),
        {
            name: load_scenario(ROOT / "scenarios" / f"{name}.yaml")
            for name in (
                "prompt_injection",
                "tool_governance",
                "data_confidentiality",
            )
        },
        {"token"},
    )

    entry = await executor(case)

    assert entry.evaluation is not None
    assert entry.evaluation.verdict == Verdict.ERROR
    assert entry.rule_evaluation is not None
    assert entry.rule_evaluation.verdict == Verdict.PASS
    assert entry.candidate is not None
    assert len(entry.responses) == 1
    assert len(entry.steps) == 1
    assert entry.model_judgment is None
    assert entry.error_stage == "independent_judgment"
    assert entry.error_type == "ValueError"


@pytest.mark.asyncio
async def test_agent_reference_preserves_candidate_when_agent_execution_fails(
    monkeypatch,
) -> None:
    async def fail_start(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("synthetic Agent execution failure")

    monkeypatch.setattr(
        agent_reference_module,
        "execute_reference_start",
        fail_start,
    )
    case = load_reference_case(
        ROOT / "reference_cases" / "account_list_generated_instruction_case.yaml"
    )
    executor = AgentReferenceExecutor(
        _Generator(),
        _Judge(),
        {
            name: load_scenario(ROOT / "scenarios" / f"{name}.yaml")
            for name in (
                "prompt_injection",
                "tool_governance",
                "data_confidentiality",
            )
        },
        {"token"},
    )

    entry = await executor(case)

    assert entry.evaluation is not None
    assert entry.evaluation.verdict == Verdict.ERROR
    assert entry.candidate is not None
    assert entry.responses == []
    assert entry.steps == []
    assert entry.error_stage == "agent_execution"
    assert entry.error_type == "RuntimeError"


@pytest.mark.asyncio
async def test_reference_steps_reject_sensitive_intermediate_response() -> None:
    case = load_reference_case(
        ROOT / "reference_cases" / "balance_selection_resume_contract_baseline.yaml"
    )
    executor = AgentReferenceExecutor(
        _Generator(),
        _Judge(),
        {
            name: load_scenario(ROOT / "scenarios" / f"{name}.yaml")
            for name in ("prompt_injection", "tool_governance", "data_confidentiality")
        },
        {"account_number", "token"},
    )
    entry = await executor(case)
    first = entry.steps[0]
    assert first.response is not None
    contaminated = first.response.model_copy(
        update={"reply": "account_number=123456789012"}
    )
    steps = [first.model_copy(update={"response": contaminated}), *entry.steps[1:]]

    evaluation = evaluate_reference_steps(
        case,
        steps,
        redact_fields={"account_number", "token"},
        expected_execution_context_id=f"exec_{case.id}",
        expected_chat_session_id=f"chat_{case.id}",
    )

    assert evaluation.verdict == Verdict.FAIL
    assert "step_1:sensitive_values" in evaluation.evidence


@pytest.mark.asyncio
async def test_agent_reference_preserves_response_when_evaluator_returns_error(
    monkeypatch,
) -> None:
    case = load_reference_case(
        ROOT / "reference_cases" / "account_list_contract_baseline.yaml"
    )

    def error_evaluation(*args, **kwargs):
        del args, kwargs
        return ReferenceCaseEvaluation(
            case_id=case.id,
            verdict=Verdict.ERROR,
            reason="execution evidence is missing",
        )

    monkeypatch.setattr(
        agent_reference_module,
        "evaluate_reference_steps",
        error_evaluation,
    )
    executor = AgentReferenceExecutor(
        _Generator(),
        _Judge(),
        {
            name: load_scenario(ROOT / "scenarios" / f"{name}.yaml")
            for name in ("prompt_injection", "tool_governance", "data_confidentiality")
        },
        {"token"},
    )

    entry = await executor(case)

    assert entry.evaluation is not None
    assert entry.evaluation.verdict == Verdict.ERROR
    assert entry.rule_evaluation is not None
    assert entry.responses
    assert entry.steps
    assert entry.error_stage == "evidence_validation"


@pytest.mark.asyncio
async def test_agent_reference_preserves_response_when_evaluator_raises(
    monkeypatch,
) -> None:
    case = load_reference_case(
        ROOT / "reference_cases" / "account_list_generated_instruction_case.yaml"
    )

    def fail_evaluation(*args, **kwargs):
        del args, kwargs
        raise ValueError("synthetic rule evaluator failure")

    monkeypatch.setattr(
        agent_reference_module,
        "evaluate_reference_steps",
        fail_evaluation,
    )
    executor = AgentReferenceExecutor(
        _Generator(),
        _Judge(),
        {
            name: load_scenario(ROOT / "scenarios" / f"{name}.yaml")
            for name in ("prompt_injection", "tool_governance", "data_confidentiality")
        },
        {"token"},
    )

    entry = await executor(case)

    assert entry.candidate is not None
    assert entry.responses
    assert entry.steps
    assert entry.error_stage == "rule_evaluation"


@pytest.mark.asyncio
async def test_agent_reference_isolation_preserves_first_completed_run(
    monkeypatch,
) -> None:
    original = agent_reference_module.execute_reference_start
    calls = 0

    async def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("synthetic second isolation failure")
        return await original(*args, **kwargs)

    monkeypatch.setattr(
        agent_reference_module,
        "execute_reference_start",
        fail_second,
    )
    case = load_reference_case(
        ROOT / "reference_cases" / "account_list_conversation_isolation.yaml"
    )
    executor = AgentReferenceExecutor(
        _Generator(),
        _Judge(),
        {
            name: load_scenario(ROOT / "scenarios" / f"{name}.yaml")
            for name in ("prompt_injection", "tool_governance", "data_confidentiality")
        },
        {"token"},
    )

    entry = await executor(case)

    assert len(entry.responses) == 1
    assert len(entry.steps) == 1
    assert entry.error_stage == "agent_execution"


@pytest.mark.asyncio
async def test_agent_reference_preserves_evidence_on_backend_verification_failure() -> (
    None
):
    case = load_reference_case(
        ROOT / "reference_cases" / "account_list_generated_instruction_case.yaml"
    )
    executor = AgentReferenceExecutor(
        _Generator(),
        _Judge(),
        {
            name: load_scenario(ROOT / "scenarios" / f"{name}.yaml")
            for name in ("prompt_injection", "tool_governance", "data_confidentiality")
        },
        {"token"},
    )
    backend_type = executor._api.mock_backend

    class FailingBackend(backend_type):
        def assert_all_responses_used(self) -> None:
            raise AssertionError("synthetic backend verification failure")

    executor._api = replace(executor._api, mock_backend=FailingBackend)

    entry = await executor(case)

    assert entry.candidate is not None
    assert entry.responses
    assert entry.steps
    assert entry.rule_evaluation is not None
    assert entry.error_stage == "backend_verification"


@pytest.mark.asyncio
async def test_agent_reference_bounds_hanging_testbed_execution(monkeypatch) -> None:
    async def hang(*args, **kwargs):
        del args, kwargs
        await asyncio.Event().wait()

    monkeypatch.setattr(agent_reference_module, "execute_reference_start", hang)
    case = load_reference_case(
        ROOT / "reference_cases" / "account_list_contract_baseline.yaml"
    )
    executor = AgentReferenceExecutor(
        _Generator(),
        _Judge(),
        {
            name: load_scenario(ROOT / "scenarios" / f"{name}.yaml")
            for name in ("prompt_injection", "tool_governance", "data_confidentiality")
        },
        {"token"},
        RequestBudget(10, 0.1),
    )

    entry = await executor(case)

    assert entry.evaluation is not None
    assert entry.evaluation.verdict == Verdict.ERROR
    assert entry.error_stage == "agent_execution_timeout"


@pytest.mark.asyncio
async def test_agent_reference_closes_coroutine_when_budget_already_expired() -> None:
    budget = RequestBudget(10, 0.001)
    executor = AgentReferenceExecutor(
        _Generator(),
        _Judge(),
        {
            name: load_scenario(ROOT / "scenarios" / f"{name}.yaml")
            for name in ("prompt_injection", "tool_governance", "data_confidentiality")
        },
        {"token"},
        budget,
    )

    async def never_started() -> None:
        raise AssertionError("expired budget must not start the coroutine")

    await asyncio.sleep(0.01)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with pytest.raises(RequestBudgetError, match="deadline exhausted"):
            await executor._bounded(never_started())

    assert not [warning for warning in caught if "was never awaited" in str(warning)]


@pytest.mark.asyncio
async def test_agent_reference_preserves_inner_timeout_provenance() -> None:
    executor = AgentReferenceExecutor(
        _Generator(),
        _Judge(),
        {
            name: load_scenario(ROOT / "scenarios" / f"{name}.yaml")
            for name in ("prompt_injection", "tool_governance", "data_confidentiality")
        },
        {"token"},
        RequestBudget(10, 1),
    )

    async def fail_locally() -> None:
        raise TimeoutError("case-local timeout")

    with pytest.raises(TimeoutError, match="case-local timeout"):
        await executor._bounded(fail_locally())


@pytest.mark.asyncio
async def test_campaign_timeout_preserves_generated_candidate_telemetry() -> None:
    case = load_reference_case(
        ROOT / "reference_cases" / "account_list_generated_instruction_case.yaml"
    )
    generator = _Generator()
    judge = _Judge()
    executor = AgentReferenceExecutor(
        generator,
        judge,
        {
            name: load_scenario(ROOT / "scenarios" / f"{name}.yaml")
            for name in ("prompt_injection", "tool_governance", "data_confidentiality")
        },
        {"token"},
    )

    async def generate_then_hang(active_case: ReferenceCase):
        executor._active_case_id = active_case.id
        executor._active_candidate = executor._generate(active_case)
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    result = await run_reference_campaign(
        [case],
        generate_then_hang,
        metadata_factory=lambda: _metadata(
            [case], generator, judge, executor.agent_source_commit
        ),
        remaining_seconds=lambda: 0.01,
        timeout_entry_factory=executor.timeout_entry,
    )

    assert result.entries[0].candidate is not None
    assert result.metadata.generator_telemetry.successes == 1


@pytest.mark.asyncio
async def test_campaign_timeout_preserves_prior_adaptive_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = load_reference_case(
        ROOT / "reference_cases" / "account_list_generated_instruction_case.yaml"
    )
    generator = _Generator()
    judge = _Judge()
    executor = AgentReferenceExecutor(
        generator,
        judge,
        {
            name: load_scenario(ROOT / "scenarios" / f"{name}.yaml")
            for name in ("prompt_injection", "tool_governance", "data_confidentiality")
        },
        {"token"},
        max_iterations_per_generated_case=3,
    )
    original_execute_once = executor._execute_once
    calls = 0

    async def complete_once_then_hang(active_case: ReferenceCase):
        nonlocal calls
        calls += 1
        if calls == 1:
            return await original_execute_once(active_case)
        executor._active_candidate = executor._generate(active_case)
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    monkeypatch.setattr(executor, "_execute_once", complete_once_then_hang)
    result = await run_reference_campaign(
        [case],
        executor,
        metadata_factory=lambda: _metadata(
            [case], generator, judge, executor.agent_source_commit
        ),
        remaining_seconds=lambda: 0.05,
        timeout_entry_factory=executor.timeout_entry,
    )

    entry = result.entries[0]
    assert len(entry.adaptive_attempts) == 2
    assert entry.adaptive_attempts[0].evaluation.verdict == Verdict.PASS
    assert entry.adaptive_attempts[1].evaluation.verdict == Verdict.ERROR
    assert result.metadata.generator_telemetry.successes == 2
    assert result.metadata.judgment_telemetry.successes == 1


def test_timeout_entry_flattens_live_isolation_step_groups() -> None:
    case = load_reference_case(
        ROOT / "reference_cases" / "set_alias_conversation_isolation.yaml"
    )
    executor = AgentReferenceExecutor(
        _Generator(),
        _Judge(),
        {
            name: load_scenario(ROOT / "scenarios" / f"{name}.yaml")
            for name in ("prompt_injection", "tool_governance", "data_confidentiality")
        },
        {"token"},
    )
    response = AgentResponse(status="completed", reply="ok", thread_id="thread")
    first_steps = [
        agent_reference_module._response_step(ReferenceOperationKind.START, response)
    ]
    second_steps = [
        agent_reference_module._response_step(ReferenceOperationKind.START, response)
    ]
    executor._active_case_id = case.id
    executor._active_step_groups = [first_steps, second_steps]
    second_steps.append(
        agent_reference_module._response_step(
            ReferenceOperationKind.APPROVAL_RESUME,
            response,
        )
    )

    entry = executor.timeout_entry(case, TimeoutError("deadline"))

    assert len(entry.steps) == 3
