"""LangGraph 실행, HITL 중단과 검증된 Resume을 연결하는 공통 Runtime."""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command, StateSnapshot
from pydantic import BaseModel, ConfigDict, Field

from agent.runtime.hitl import ExecutionResumeRequest, ExecutionStartRequest
from agent.runtime.interaction_pause import InteractionPauseRuntime
from agent.runtime.resume_state_mapper import ResumeStateMapper
from agent.runtime.resume_validation import (
    ExecutionContextBinding,
    ResumeValidationRuntime,
)

logger = logging.getLogger(__name__)

ExecutionStatus = Literal["accepted", "running", "waiting", "completed", "failed"]
ExecutionRuntimeErrorCode = Literal[
    "EXECUTION_NOT_FOUND",
    "EXECUTION_NOT_WAITING",
    "RESUME_NOT_ACCEPTED",
    "START_REQUEST_ID_CONFLICT",
    "RESUME_REQUEST_ID_CONFLICT",
    "THREAD_ID_COLLISION",
    "INTERRUPT_NOT_FOUND",
    "MULTIPLE_INTERRUPTS",
    "INVALID_INTERRUPT_PAYLOAD",
]


class ExecutionGraph(Protocol):
    """Execution Runtime이 사용하는 LangGraph 최소 실행 표면."""

    async def ainvoke(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]: ...

    async def aget_state(
        self,
        config: RunnableConfig,
        *,
        subgraphs: bool = False,
    ) -> StateSnapshot: ...


class ExecutionFailureReporter(Protocol):
    """실행 실패를 외부 채널에 안전한 형태로 알리는 최소 경계."""

    async def report_failure(
        self,
        *,
        agent_thread_id: str,
        chat_session_id: str,
        execution_context_id: str,
        request_id: str,
    ) -> None: ...


class ExecutionCompletionReporter(Protocol):
    """정상 종료한 실행 턴을 외부 채널에 알리는 최소 경계."""

    async def report_completion(
        self,
        *,
        agent_thread_id: str,
        chat_session_id: str,
        execution_context_id: str,
        request_id: str,
    ) -> str: ...


class ExecutionAccepted(BaseModel):
    """실행 요청 접수 결과."""

    model_config = ConfigDict(extra="forbid")

    accepted: Literal[True] = True
    agent_thread_id: str = Field(min_length=1)
    replayed: bool = False


class ExecutionRunResult(BaseModel):
    """HTTP 응답이 아닌 Agent 내부 실행 경계의 처리 결과."""

    model_config = ConfigDict(extra="forbid")

    agent_thread_id: str = Field(min_length=1)
    status: ExecutionStatus
    pending_interaction: dict[str, Any] | None = None
    webhook_message_id: str | None = None
    replayed: bool = False


class ExecutionResumeAccepted(BaseModel):
    """검증을 마치고 백그라운드 Graph 재개를 접수한 결과."""

    model_config = ConfigDict(extra="forbid")

    accepted: Literal[True] = True
    agent_thread_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    replayed: bool = False


class ExecutionRuntimeError(RuntimeError):
    """실행 생명주기 또는 Checkpoint 상태가 요청과 일치하지 않는 경우."""

    def __init__(
        self,
        *,
        code: ExecutionRuntimeErrorCode,
        reason: str,
    ) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


@dataclass
class _ExecutionRecord:
    start_request: ExecutionStartRequest
    binding: ExecutionContextBinding
    status: ExecutionStatus = "accepted"
    pending_interaction: dict[str, Any] | None = None
    webhook_message_id: str | None = None
    active_resume_request_id: str | None = None
    resume_requests: dict[str, ExecutionResumeRequest] = field(default_factory=dict)
    prepared_resumes: dict[str, _PreparedResume] = field(default_factory=dict)
    started_resume_request_ids: set[str] = field(default_factory=set)
    resume_results: dict[str, ExecutionRunResult] = field(default_factory=dict)


@dataclass(frozen=True)
class _PreparedResume:
    state_values: dict[str, Any]


class ExecutionRuntime:
    """실행 식별자와 Checkpoint를 묶고 HITL Webhook을 한 번만 발행한다."""

    def __init__(
        self,
        *,
        graph: ExecutionGraph,
        interaction_runtime: InteractionPauseRuntime,
        resume_mapper: ResumeStateMapper,
        failure_reporter: ExecutionFailureReporter | None = None,
        completion_reporter: ExecutionCompletionReporter | None = None,
        thread_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._graph = graph
        self._interaction_runtime = interaction_runtime
        self._resume_mapper = resume_mapper
        self._failure_reporter = failure_reporter
        self._completion_reporter = completion_reporter
        self._thread_id_factory = thread_id_factory or (lambda: uuid.uuid4().hex)
        self._lock = threading.RLock()
        self._records: dict[str, _ExecutionRecord] = {}
        self._start_request_threads: dict[str, str] = {}

    def accept_start(self, request: ExecutionStartRequest) -> ExecutionAccepted:
        """중복 시작 요청에 같은 Thread를 반환하고 새 실행만 접수한다."""

        with self._lock:
            existing_thread_id = self._start_request_threads.get(request.request_id)
            if existing_thread_id is not None:
                existing = self._records[existing_thread_id]
                if existing.start_request != request:
                    raise ExecutionRuntimeError(
                        code="START_REQUEST_ID_CONFLICT",
                        reason=(
                            "같은 request_id에 다른 실행 시작 요청을 "
                            "사용할 수 없습니다."
                        ),
                    )
                return ExecutionAccepted(
                    agent_thread_id=existing_thread_id,
                    replayed=True,
                )

            thread_id = self._thread_id_factory()
            if not thread_id:
                raise ExecutionRuntimeError(
                    code="THREAD_ID_COLLISION",
                    reason="빈 Agent Thread ID를 생성할 수 없습니다.",
                )
            if thread_id in self._records:
                raise ExecutionRuntimeError(
                    code="THREAD_ID_COLLISION",
                    reason="이미 사용 중인 Agent Thread ID가 생성됐습니다.",
                )

            binding = ExecutionContextBinding(
                agent_thread_id=thread_id,
                chat_session_id=request.chat_session_id,
                execution_context_id=request.execution_context_id,
            )
            self._records[thread_id] = _ExecutionRecord(
                start_request=request,
                binding=binding,
            )
            self._start_request_threads[request.request_id] = thread_id
            return ExecutionAccepted(agent_thread_id=thread_id)

    async def start(
        self,
        request: ExecutionStartRequest,
        *,
        initial_state: Mapping[str, Any] | None = None,
    ) -> ExecutionRunResult:
        """새 실행을 접수하고 LangGraph가 중단 또는 종료할 때까지 실행한다."""

        accepted = self.accept_start(request)
        return await self.run_accepted(
            accepted.agent_thread_id,
            initial_state=initial_state,
        )

    async def run_accepted(
        self,
        agent_thread_id: str,
        *,
        initial_state: Mapping[str, Any] | None = None,
    ) -> ExecutionRunResult:
        """별도 HTTP 계층에서 먼저 접수한 실행을 실제로 시작한다."""

        with self._lock:
            record = self._get_record(agent_thread_id)
            if record.status != "accepted":
                return self._result_from_record(record, replayed=True)
            record.status = "running"

        state = dict(initial_state or self._initial_state(record.start_request))
        try:
            result = await self._graph.ainvoke(
                state,
                config=self._config(record.binding, record.start_request.request_id),
            )
            return await self._finish_invocation(
                record,
                result=result,
                request_id=record.start_request.request_id,
            )
        except Exception:
            with self._lock:
                record.status = "failed"
                record.pending_interaction = None
            await self._report_failure(
                record,
                request_id=record.start_request.request_id,
            )
            raise

    async def resume(
        self,
        agent_thread_id: str,
        request: ExecutionResumeRequest,
    ) -> ExecutionRunResult:
        """Resume 검증·접수와 실제 Graph 재개를 한 번에 수행한다."""

        accepted = await self.accept_resume(agent_thread_id, request)
        if accepted.replayed:
            with self._lock:
                record = self._get_record(agent_thread_id)
                replayed = self._replayed_resume(record, request)
                if replayed is not None:
                    return replayed
        return await self.run_accepted_resume(agent_thread_id, request.request_id)

    async def accept_resume(
        self,
        agent_thread_id: str,
        request: ExecutionResumeRequest,
    ) -> ExecutionResumeAccepted:
        """현재 Pending을 검증하고 하나의 Resume 요청만 실행 대상으로 접수한다."""

        with self._lock:
            record = self._get_record(agent_thread_id)
            replayed = self._replayed_resume(record, request)
            if replayed is not None:
                return ExecutionResumeAccepted(
                    agent_thread_id=agent_thread_id,
                    request_id=request.request_id,
                    replayed=True,
                )
            if record.status != "waiting":
                raise ExecutionRuntimeError(
                    code="EXECUTION_NOT_WAITING",
                    reason="현재 사용자 입력을 기다리는 실행이 아닙니다.",
                )

        config = self._config(record.binding, request.request_id)
        snapshot = await self._graph.aget_state(config)
        interrupt_payload = self._single_interrupt_payload(snapshot.interrupts)
        validated = ResumeValidationRuntime.validate(
            agent_thread_id=agent_thread_id,
            request=request,
            binding=record.binding,
            interrupt_payload=interrupt_payload,
        )
        state_update = self._resume_mapper.map(validated)

        with self._lock:
            replayed = self._replayed_resume(record, request)
            if replayed is not None:
                return ExecutionResumeAccepted(
                    agent_thread_id=agent_thread_id,
                    request_id=request.request_id,
                    replayed=True,
                )
            if record.status != "waiting":
                raise ExecutionRuntimeError(
                    code="EXECUTION_NOT_WAITING",
                    reason="다른 Resume 요청이 이미 실행을 재개했습니다.",
                )
            record.status = "running"
            record.active_resume_request_id = request.request_id
            record.resume_requests[request.request_id] = request
            record.prepared_resumes[request.request_id] = _PreparedResume(
                state_values=state_update.values,
            )
            return ExecutionResumeAccepted(
                agent_thread_id=agent_thread_id,
                request_id=request.request_id,
            )

    async def run_accepted_resume(
        self,
        agent_thread_id: str,
        request_id: str,
    ) -> ExecutionRunResult:
        """검증과 접수를 마친 Resume으로 LangGraph를 실제 재개한다."""

        with self._lock:
            record = self._get_record(agent_thread_id)
            existing_result = record.resume_results.get(request_id)
            if existing_result is not None:
                return existing_result.model_copy(update={"replayed": True})
            prepared = record.prepared_resumes.get(request_id)
            if prepared is None or record.active_resume_request_id != request_id:
                raise ExecutionRuntimeError(
                    code="RESUME_NOT_ACCEPTED",
                    reason="검증과 접수를 마친 Resume 요청이 아닙니다.",
                )
            if request_id in record.started_resume_request_ids:
                return self._result_from_record(record, replayed=True)
            record.started_resume_request_ids.add(request_id)

        config = self._config(record.binding, request_id)

        try:
            result = await self._graph.ainvoke(
                Command(resume=prepared.state_values),
                config=config,
            )
            run_result = await self._finish_invocation(
                record,
                result=result,
                request_id=request_id,
            )
            with self._lock:
                record.active_resume_request_id = None
                record.resume_results[request_id] = run_result
            return run_result
        except Exception:
            with self._lock:
                record.status = "failed"
                record.pending_interaction = None
                record.active_resume_request_id = None
            await self._report_failure(record, request_id=request_id)
            raise

    async def _report_failure(
        self,
        record: _ExecutionRecord,
        *,
        request_id: str,
    ) -> None:
        reporter = self._failure_reporter
        if reporter is None:
            return
        try:
            await reporter.report_failure(
                agent_thread_id=record.binding.agent_thread_id,
                chat_session_id=record.binding.chat_session_id,
                execution_context_id=record.binding.execution_context_id,
                request_id=request_id,
            )
        except Exception:
            logger.exception(
                "Agent Workflow 실패 Webhook 전송에 실패했습니다.",
                extra={
                    "agent_thread_id": record.binding.agent_thread_id,
                    "request_id": request_id,
                },
            )

    async def _finish_invocation(
        self,
        record: _ExecutionRecord,
        *,
        result: Mapping[str, Any],
        request_id: str,
    ) -> ExecutionRunResult:
        interrupt_payload = self._interrupt_payload_from_result(result)
        if interrupt_payload is None:
            if result.get("status") == "workflow_failed":
                # Workflow 오류 노드가 업무별 안전한 error Webhook을 이미 보냈다.
                # Runtime은 실패 상태만 확정하고 error/done을 중복 전송하지 않는다.
                with self._lock:
                    record.status = "failed"
                    record.pending_interaction = None
                    record.webhook_message_id = None
                    return self._result_from_record(record)

            completion_message_id = await self._report_completion(
                record,
                result=result,
                request_id=request_id,
            )
            with self._lock:
                record.status = "completed"
                record.pending_interaction = None
                record.webhook_message_id = completion_message_id
                return self._result_from_record(record)

        published = await self._interaction_runtime.publish_interrupted(
            interrupt_payload,
            execution_context_id=record.binding.execution_context_id,
            request_id=request_id,
        )
        pending = published.pending_interaction.model_dump(mode="json")
        with self._lock:
            record.status = "waiting"
            record.pending_interaction = pending
            record.webhook_message_id = published.message_id
            return self._result_from_record(record)

    async def _report_completion(
        self,
        record: _ExecutionRecord,
        *,
        result: Mapping[str, Any],
        request_id: str,
    ) -> str | None:
        reporter = self._completion_reporter
        if (
            reporter is None
            or result.get("route_key") == "cancelled"
            or result.get("status") == "blocked"
        ):
            # 취소는 Backend가 사용자 요청 시점에 Stream을 닫고, blocked는
            # Workflow가 보낸 blocked Webhook 자체를 Backend가 terminal로 처리한다.
            return None
        try:
            return await reporter.report_completion(
                agent_thread_id=record.binding.agent_thread_id,
                chat_session_id=record.binding.chat_session_id,
                execution_context_id=record.binding.execution_context_id,
                request_id=request_id,
            )
        except Exception:
            logger.exception(
                "Agent Workflow 완료 Webhook 전송에 실패했습니다.",
                extra={
                    "agent_thread_id": record.binding.agent_thread_id,
                    "request_id": request_id,
                },
            )
            return None

    def _replayed_resume(
        self,
        record: _ExecutionRecord,
        request: ExecutionResumeRequest,
    ) -> ExecutionRunResult | None:
        existing_request = record.resume_requests.get(request.request_id)
        if existing_request is None:
            return None
        if existing_request != request:
            raise ExecutionRuntimeError(
                code="RESUME_REQUEST_ID_CONFLICT",
                reason="같은 request_id에 다른 Resume 요청을 사용할 수 없습니다.",
            )
        existing_result = record.resume_results.get(request.request_id)
        if existing_result is not None:
            return existing_result.model_copy(update={"replayed": True})
        return self._result_from_record(record, replayed=True)

    def _get_record(self, agent_thread_id: str) -> _ExecutionRecord:
        record = self._records.get(agent_thread_id)
        if record is None:
            raise ExecutionRuntimeError(
                code="EXECUTION_NOT_FOUND",
                reason="Agent Thread에 연결된 실행을 찾을 수 없습니다.",
            )
        return record

    @staticmethod
    def _initial_state(request: ExecutionStartRequest) -> dict[str, Any]:
        return {
            "user_input": request.message,
            "status": "start",
            "data": {},
            "logs": [],
            "execution_trace": [],
        }

    @staticmethod
    def _config(
        binding: ExecutionContextBinding,
        request_id: str,
    ) -> RunnableConfig:
        return {
            "configurable": {
                "thread_id": binding.agent_thread_id,
                "chat_session_id": binding.chat_session_id,
                "execution_context_id": binding.execution_context_id,
                "request_id": request_id,
            }
        }

    @staticmethod
    def _interrupt_payload_from_result(
        result: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        interrupts = result.get("__interrupt__")
        if not interrupts:
            return None
        if not isinstance(interrupts, (list, tuple)):
            raise ExecutionRuntimeError(
                code="INVALID_INTERRUPT_PAYLOAD",
                reason="LangGraph Interrupt 목록 형식이 올바르지 않습니다.",
            )
        return ExecutionRuntime._single_interrupt_payload(interrupts)

    @staticmethod
    def _single_interrupt_payload(interrupts: Any) -> dict[str, Any]:
        if not isinstance(interrupts, (list, tuple)) or not interrupts:
            raise ExecutionRuntimeError(
                code="INTERRUPT_NOT_FOUND",
                reason="현재 Checkpoint에 대기 중인 Interrupt가 없습니다.",
            )
        if len(interrupts) != 1:
            raise ExecutionRuntimeError(
                code="MULTIPLE_INTERRUPTS",
                reason="한 Agent Thread에는 하나의 활성 Interrupt만 허용합니다.",
            )
        payload = getattr(interrupts[0], "value", None)
        if not isinstance(payload, Mapping):
            raise ExecutionRuntimeError(
                code="INVALID_INTERRUPT_PAYLOAD",
                reason="LangGraph Interrupt Payload 형식이 올바르지 않습니다.",
            )
        return dict(payload)

    @staticmethod
    def _result_from_record(
        record: _ExecutionRecord,
        *,
        replayed: bool = False,
    ) -> ExecutionRunResult:
        return ExecutionRunResult(
            agent_thread_id=record.binding.agent_thread_id,
            status=record.status,
            pending_interaction=record.pending_interaction,
            webhook_message_id=record.webhook_message_id,
            replayed=replayed,
        )
