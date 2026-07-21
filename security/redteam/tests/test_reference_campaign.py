import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest

from security.redteam.models import (
    AgentResponse,
    AttackerTelemetry,
    BusinessWorkflow,
    JudgmentTelemetry,
    Verdict,
)
from security.redteam.runner.client import RequestBudgetError
from security.redteam.runner.reference_campaign import (
    ReferenceCampaignEntry,
    ReferenceCampaignMetadata,
    ReferenceCampaignResult,
    ReferenceExecutionStep,
    ReferenceOperationKind,
    run_reference_campaign,
)
from security.redteam.runner.reference_cases import (
    ReferenceCase,
    ReferenceCaseEvaluation,
    ReferenceExecutionKind,
    load_reference_case,
)
from security.redteam.runner.reporter import write_reference_campaign_report


def _case(case_id: str, workflow: BusinessWorkflow) -> ReferenceCase:
    return ReferenceCase(
        version=1,
        id=case_id,
        target_workflow_id=workflow,
        execution_kind=ReferenceExecutionKind.SINGLE,
        message="로컬 확인",
        expected_public_statuses={"completed"},
        expected_runtime_statuses={"completed"},
        expected_state_statuses={"completed"},
    )


def _metadata() -> ReferenceCampaignMetadata:
    return ReferenceCampaignMetadata(
        agent_source_commit="e867ccb",
        case_set_kind="default",
        runner_git_commit="a" * 40,
        runner_git_dirty=True,
        config_sha256="b" * 64,
        case_set_sha256="c" * 64,
        generator_model="fixture-generator",
        generator_model_digest="d" * 64,
        judgment_model="fixture-judge",
        judgment_model_digest="e" * 64,
        generator_telemetry=AttackerTelemetry(
            model="fixture-generator",
            attempts=0,
            successes=0,
            failures=0,
            rejected_out_of_scope=0,
        ),
        judgment_telemetry=JudgmentTelemetry(
            model="fixture-judge",
            attempts=0,
            successes=0,
            failures=0,
            agreements=0,
            disagreements=0,
            uncertain=0,
        ),
    )


def _response() -> AgentResponse:
    return AgentResponse(status="completed", reply="ok", thread_id="thread-1")


@pytest.mark.asyncio
async def test_reference_campaign_sorts_and_counts_explicit_results(tmp_path) -> None:
    cases = [
        _case("z_case", BusinessWorkflow.BALANCE_INQUIRY),
        _case("a_case", BusinessWorkflow.ACCOUNT_LIST),
    ]

    async def execute(case: ReferenceCase) -> ReferenceCampaignEntry:
        if case.id == "z_case":
            return ReferenceCampaignEntry(
                case_id=case.id,
                workflow_id=case.target_workflow_id,
                case_contract=case,
                status="not_supported",
                note="Agent resume dependency is pending",
            )
        return ReferenceCampaignEntry(
            case_id=case.id,
            workflow_id=case.target_workflow_id,
            case_contract=case,
            status="executed",
            evaluation=ReferenceCaseEvaluation(
                case_id=case.id,
                verdict=Verdict.PASS,
                reason="contract matched",
            ),
            responses=[_response()],
            steps=[
                ReferenceExecutionStep(
                    operation=ReferenceOperationKind.START,
                    response=_response(),
                )
            ],
        )

    result = await run_reference_campaign(
        cases,
        execute,
        metadata_factory=_metadata,
        started_at=datetime(2026, 7, 21, tzinfo=UTC),
    )

    assert [entry.case_id for entry in result.entries] == ["a_case", "z_case"]
    assert result.totals == {
        "executed": 1,
        "not_supported": 1,
        "not_executed": 0,
        "PASS": 1,
        "FAIL": 0,
        "ERROR": 0,
        "review_required": 0,
    }
    json_path, markdown_path = write_reference_campaign_report(
        result,
        tmp_path,
        {"token"},
    )
    assert json_path.is_file()
    assert markdown_path.is_file()
    assert json_path.with_suffix(".complete").is_file()
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "| `a_case`" in markdown
    assert "Agent source commit: `e867ccb`" in markdown
    assert "Case set kind: `default`" in markdown
    assert "Custom case sets are exploratory" not in markdown
    payload = json_path.read_text(encoding="utf-8")
    assert '"case_contract"' in payload
    assert '"report_schema_version": 3' in payload
    assert '"responses"' not in payload
    assert '"runner_git_dirty": true' in payload


@pytest.mark.asyncio
async def test_custom_reference_campaign_markdown_marks_provenance(tmp_path) -> None:
    case = _case("custom_case", BusinessWorkflow.ACCOUNT_LIST)

    async def execute(_case: ReferenceCase) -> ReferenceCampaignEntry:
        response = _response()
        return ReferenceCampaignEntry(
            case_id=case.id,
            workflow_id=case.target_workflow_id,
            case_contract=case,
            status="executed",
            evaluation=ReferenceCaseEvaluation(
                case_id=case.id,
                verdict=Verdict.PASS,
                reason="contract matched",
            ),
            responses=[response],
            steps=[
                ReferenceExecutionStep(
                    operation=ReferenceOperationKind.START,
                    response=response,
                )
            ],
        )

    metadata = _metadata().model_copy(update={"case_set_kind": "custom"})
    result = await run_reference_campaign(
        [case],
        execute,
        metadata_factory=lambda: metadata,
    )
    _, markdown_path = write_reference_campaign_report(result, tmp_path, {"token"})
    markdown = markdown_path.read_text(encoding="utf-8")

    assert "Case set kind: `custom`" in markdown
    assert "Custom case sets are exploratory" in markdown
    assert "Case set SHA-256: `" in markdown


@pytest.mark.asyncio
async def test_reference_markdown_shows_bounded_error_details(tmp_path) -> None:
    case = _case("error_case", BusinessWorkflow.ACCOUNT_LIST)

    async def execute(_case: ReferenceCase) -> ReferenceCampaignEntry:
        return ReferenceCampaignEntry(
            case_id=case.id,
            workflow_id=case.target_workflow_id,
            case_contract=case,
            status="executed",
            evaluation=ReferenceCaseEvaluation(
                case_id=case.id,
                verdict=Verdict.ERROR,
                reason="independent judgment failed",
            ),
            rule_evaluation=ReferenceCaseEvaluation(
                case_id=case.id,
                verdict=Verdict.PASS,
                reason="contract matched",
            ),
            review_required=True,
            error_stage="independent_judgment",
            error_type="ValueError",
            error_reason="independent judgment failed after bounded retries",
        )

    result = await run_reference_campaign(
        [case],
        execute,
        metadata_factory=_metadata,
    )
    _, markdown_path = write_reference_campaign_report(result, tmp_path, {"token"})
    markdown = markdown_path.read_text(encoding="utf-8")

    assert "independent_judgment" in markdown
    assert "independent judgment failed after bounded retries" in markdown
    assert "| `ERROR` | `PASS` |" in markdown


def test_reference_campaign_rejects_executed_entry_without_evaluation() -> None:
    case = _case("missing_result", BusinessWorkflow.ACCOUNT_LIST)
    with pytest.raises(ValueError, match="requires an evaluation"):
        ReferenceCampaignEntry(
            case_id="missing_result",
            workflow_id=BusinessWorkflow.ACCOUNT_LIST,
            case_contract=case,
            status="executed",
        )


def test_reference_campaign_rejects_unsupported_entry_with_run_result() -> None:
    case = _case("unsupported_result", BusinessWorkflow.ACCOUNT_LIST)
    with pytest.raises(ValueError, match="cannot contain run results"):
        ReferenceCampaignEntry(
            case_id="unsupported_result",
            workflow_id=BusinessWorkflow.ACCOUNT_LIST,
            case_contract=case,
            status="not_supported",
            note="dependency pending",
            evaluation=ReferenceCaseEvaluation(
                case_id="unsupported_result",
                verdict=Verdict.PASS,
                reason="invalid mixed state",
            ),
        )


def test_generated_campaign_entry_requires_candidate_and_independent_judgment() -> None:
    case = load_reference_case(
        Path(__file__).resolve().parents[1]
        / "reference_cases"
        / "account_list_generated_instruction_case.yaml"
    )
    response = _response()

    with pytest.raises(ValueError, match="requires generation results"):
        ReferenceCampaignEntry(
            case_id=case.id,
            workflow_id=case.target_workflow_id,
            case_contract=case,
            status="executed",
            evaluation=ReferenceCaseEvaluation(
                case_id=case.id,
                verdict=Verdict.PASS,
                reason="contract matched",
            ),
            responses=[response],
            steps=[
                ReferenceExecutionStep(
                    operation=ReferenceOperationKind.START,
                    response=response,
                )
            ],
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("case_count", [2, 101])
async def test_reference_campaign_rejects_ambiguous_or_unbounded_cases(
    case_count: int,
) -> None:
    case = _case("same_case", BusinessWorkflow.ACCOUNT_LIST)
    cases = [case] * case_count

    async def never_execute(_case: ReferenceCase) -> ReferenceCampaignEntry:
        raise AssertionError("invalid campaign must fail before execution")

    match = "unique" if case_count == 2 else "at most 100"
    with pytest.raises(ValueError, match=match):
        await run_reference_campaign(cases, never_execute, metadata_factory=_metadata)


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout_index", [0, 1, 2])
async def test_reference_campaign_bounds_arbitrary_hanging_executor(
    timeout_index: int,
) -> None:
    cases = [
        _case(f"case_{index}", BusinessWorkflow.ACCOUNT_LIST) for index in range(3)
    ]

    async def execute(case: ReferenceCase) -> ReferenceCampaignEntry:
        if case.id == f"case_{timeout_index}":
            await asyncio.Event().wait()
            raise AssertionError("unreachable")
        response = _response()
        return ReferenceCampaignEntry(
            case_id=case.id,
            workflow_id=case.target_workflow_id,
            case_contract=case,
            status="executed",
            evaluation=ReferenceCaseEvaluation(
                case_id=case.id,
                verdict=Verdict.PASS,
                reason="contract matched",
            ),
            responses=[response],
            steps=[
                ReferenceExecutionStep(
                    operation=ReferenceOperationKind.START,
                    response=response,
                )
            ],
        )

    result = await run_reference_campaign(
        cases,
        execute,
        metadata_factory=_metadata,
        remaining_seconds=lambda: 0.01,
    )

    assert result.requested_cases == 3
    assert len(result.entries) == 3
    assert [entry.case_id for entry in result.entries] == [case.id for case in cases]
    assert result.entries[timeout_index].error_stage == "campaign_timeout"
    assert all(
        entry.status == "not_executed" for entry in result.entries[timeout_index + 1 :]
    )
    assert result.totals["not_executed"] == 2 - timeout_index
    assert result.totals["ERROR"] == 3 - timeout_index


@pytest.mark.asyncio
async def test_reference_campaign_bounds_hanging_context_exit() -> None:
    case = _case("context_exit", BusinessWorkflow.ACCOUNT_LIST)

    @asynccontextmanager
    async def hanging_context():
        try:
            yield
        finally:
            await asyncio.Event().wait()

    async def execute(_case: ReferenceCase) -> ReferenceCampaignEntry:
        async with hanging_context():
            response = _response()
            entry = ReferenceCampaignEntry(
                case_id=case.id,
                workflow_id=case.target_workflow_id,
                case_contract=case,
                status="executed",
                evaluation=ReferenceCaseEvaluation(
                    case_id=case.id,
                    verdict=Verdict.PASS,
                    reason="contract matched",
                ),
                responses=[response],
                steps=[
                    ReferenceExecutionStep(
                        operation=ReferenceOperationKind.START,
                        response=response,
                    )
                ],
            )
        return entry

    result = await run_reference_campaign(
        [case],
        execute,
        metadata_factory=_metadata,
        remaining_seconds=lambda: 0.01,
    )

    assert result.entries[0].error_stage == "campaign_timeout"


@pytest.mark.asyncio
async def test_reference_campaign_isolates_inner_timeout_and_continues() -> None:
    cases = [
        _case("case_a", BusinessWorkflow.ACCOUNT_LIST),
        _case("case_b", BusinessWorkflow.ACCOUNT_LIST),
    ]
    calls = []

    async def execute(case: ReferenceCase) -> ReferenceCampaignEntry:
        calls.append(case.id)
        if case.id == "case_a":
            raise TimeoutError("case-local timeout")
        response = _response()
        return ReferenceCampaignEntry(
            case_id=case.id,
            workflow_id=case.target_workflow_id,
            case_contract=case,
            status="executed",
            evaluation=ReferenceCaseEvaluation(
                case_id=case.id,
                verdict=Verdict.PASS,
                reason="contract matched",
            ),
            responses=[response],
            steps=[
                ReferenceExecutionStep(
                    operation=ReferenceOperationKind.START,
                    response=response,
                )
            ],
        )

    result = await run_reference_campaign(
        cases,
        execute,
        metadata_factory=_metadata,
        remaining_seconds=lambda: 1,
    )

    assert calls == ["case_a", "case_b"]
    assert result.entries[0].error_stage == "case_execution_timeout"
    assert result.entries[1].evaluation is not None
    assert result.entries[1].evaluation.verdict == Verdict.PASS


@pytest.mark.asyncio
async def test_reference_campaign_marks_prestart_expiry_not_executed() -> None:
    cases = [
        _case("case_a", BusinessWorkflow.ACCOUNT_LIST),
        _case("case_b", BusinessWorkflow.ACCOUNT_LIST),
    ]

    async def never_execute(_case: ReferenceCase) -> ReferenceCampaignEntry:
        raise AssertionError("expired campaign must not execute a case")

    def expired() -> None:
        raise RuntimeError("deadline exhausted")

    result = await run_reference_campaign(
        cases,
        never_execute,
        metadata_factory=_metadata,
        deadline_check=expired,
    )

    assert [entry.status for entry in result.entries] == [
        "not_executed",
        "not_executed",
    ]
    assert result.totals["executed"] == 0


@pytest.mark.asyncio
async def test_zero_remaining_time_does_not_enter_executor() -> None:
    case = _case("zero_deadline", BusinessWorkflow.ACCOUNT_LIST)
    called = False

    async def execute(_case: ReferenceCase) -> ReferenceCampaignEntry:
        nonlocal called
        called = True
        raise AssertionError("expired campaign must not enter executor")

    result = await run_reference_campaign(
        [case],
        execute,
        metadata_factory=_metadata,
        remaining_seconds=lambda: 0,
    )

    assert called is False
    assert result.entries[0].error_stage == "campaign_timeout"


def test_reference_report_deadline_failure_leaves_no_output(tmp_path) -> None:
    case = _case("deadline_case", BusinessWorkflow.ACCOUNT_LIST)
    response = _response()
    entry = ReferenceCampaignEntry(
        case_id=case.id,
        workflow_id=case.target_workflow_id,
        case_contract=case,
        status="executed",
        evaluation=ReferenceCaseEvaluation(
            case_id=case.id,
            verdict=Verdict.PASS,
            reason="contract matched",
        ),
        responses=[response],
        steps=[
            ReferenceExecutionStep(
                operation=ReferenceOperationKind.START,
                response=response,
            )
        ],
    )
    result = ReferenceCampaignResult(
        campaign_id="reference_aaaaaaaaaaaa",
        started_at=datetime(2026, 7, 21, tzinfo=UTC),
        completed_at=datetime(2026, 7, 21, tzinfo=UTC),
        metadata=_metadata(),
        requested_cases=1,
        entries=[entry],
        totals={
            "executed": 1,
            "not_supported": 0,
            "not_executed": 0,
            "PASS": 1,
            "FAIL": 0,
            "ERROR": 0,
            "review_required": 0,
        },
    )
    calls = 0

    def check_deadline() -> None:
        nonlocal calls
        calls += 1
        if calls == 4:
            raise RequestBudgetError("deadline exhausted")

    with pytest.raises(RequestBudgetError, match="deadline exhausted"):
        write_reference_campaign_report(
            result,
            tmp_path,
            {"token"},
            check_deadline,
        )

    assert list(tmp_path.iterdir()) == []
