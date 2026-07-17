"""Backend가 Agent Workflow 실행과 Resume을 요청하는 내부 API."""

from __future__ import annotations

import hmac
import logging
import os
from typing import Annotated, Literal, cast

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Request,
    status,
)
from pydantic import BaseModel, ConfigDict, Field

from agent.runtime import (
    ExecutionResumeRequest,
    ExecutionRuntime,
    ExecutionRuntimeError,
    ExecutionStartRequest,
    ResumeStateMappingError,
    ResumeValidationError,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/internal/v1/executions", tags=["internal-executions"])


class InternalExecutionAccepted(BaseModel):
    """Backend에 반환하는 최소 실행 접수 응답."""

    model_config = ConfigDict(extra="forbid")

    accepted: Literal[True] = True
    agent_thread_id: str = Field(min_length=1)


def require_backend_service(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Frontend Token과 분리된 Backend 서비스 Token을 검증한다."""

    expected_token = os.getenv("BACKEND_SERVICE_TOKEN")
    if not expected_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "BACKEND_SERVICE_TOKEN_NOT_CONFIGURED",
                "message": "Backend 서비스 인증이 설정되지 않았습니다.",
            },
        )

    scheme, separator, provided_token = (authorization or "").partition(" ")
    authenticated = (
        separator == " "
        and scheme.lower() == "bearer"
        and bool(provided_token)
        and hmac.compare_digest(provided_token, expected_token)
    )
    if not authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "BACKEND_SERVICE_UNAUTHORIZED",
                "message": "Backend 서비스 인증에 실패했습니다.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_execution_runtime(request: Request) -> ExecutionRuntime:
    """애플리케이션 시작 단계에서 주입한 공통 Runtime을 반환한다."""

    runtime = getattr(request.app.state, "execution_runtime", None)
    if runtime is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "EXECUTION_RUNTIME_NOT_CONFIGURED",
                "message": "Agent Execution Runtime이 준비되지 않았습니다.",
            },
        )
    return cast(ExecutionRuntime, runtime)


BackendServiceAuthorization = Annotated[None, Depends(require_backend_service)]
ExecutionRuntimeDependency = Annotated[
    ExecutionRuntime,
    Depends(get_execution_runtime),
]


@router.post(
    "",
    response_model=InternalExecutionAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_execution(
    request: ExecutionStartRequest,
    background_tasks: BackgroundTasks,
    _authorization: BackendServiceAuthorization,
    runtime: ExecutionRuntimeDependency,
) -> InternalExecutionAccepted:
    """새 실행을 접수하고 실제 Graph 실행은 응답 이후 시작한다."""

    try:
        accepted = runtime.accept_start(request)
    except ExecutionRuntimeError as error:
        raise _runtime_http_error(error) from error

    if not accepted.replayed:
        background_tasks.add_task(
            _run_start_safely,
            runtime,
            accepted.agent_thread_id,
        )
    return InternalExecutionAccepted(agent_thread_id=accepted.agent_thread_id)


@router.post(
    "/{agent_thread_id}/resume",
    response_model=InternalExecutionAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def resume_execution(
    agent_thread_id: str,
    request: ExecutionResumeRequest,
    background_tasks: BackgroundTasks,
    _authorization: BackendServiceAuthorization,
    runtime: ExecutionRuntimeDependency,
) -> InternalExecutionAccepted:
    """Resume을 검증·접수하고 실제 Graph 재개는 응답 이후 수행한다."""

    try:
        accepted = await runtime.accept_resume(agent_thread_id, request)
    except ExecutionRuntimeError as error:
        raise _runtime_http_error(error) from error
    except ResumeValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": error.code, "message": error.reason},
        ) from error
    except ResumeStateMappingError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": error.code,
                "message": "Agent Resume 계약 매핑에 실패했습니다.",
            },
        ) from error

    if not accepted.replayed:
        background_tasks.add_task(
            _run_resume_safely,
            runtime,
            agent_thread_id,
            request.request_id,
        )
    return InternalExecutionAccepted(agent_thread_id=agent_thread_id)


async def _run_start_safely(
    runtime: ExecutionRuntime,
    agent_thread_id: str,
) -> None:
    try:
        await runtime.run_accepted(agent_thread_id)
    except Exception:
        logger.exception("Agent Workflow 시작 실행에 실패했습니다.")


async def _run_resume_safely(
    runtime: ExecutionRuntime,
    agent_thread_id: str,
    request_id: str,
) -> None:
    try:
        await runtime.run_accepted_resume(agent_thread_id, request_id)
    except Exception:
        logger.exception("Agent Workflow Resume 실행에 실패했습니다.")


def _runtime_http_error(error: ExecutionRuntimeError) -> HTTPException:
    if error.code == "EXECUTION_NOT_FOUND":
        status_code = status.HTTP_404_NOT_FOUND
    elif error.code in {
        "EXECUTION_NOT_WAITING",
        "RESUME_NOT_ACCEPTED",
        "START_REQUEST_ID_CONFLICT",
        "RESUME_REQUEST_ID_CONFLICT",
        "INTERRUPT_NOT_FOUND",
    }:
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return HTTPException(
        status_code=status_code,
        detail={"code": error.code, "message": error.reason},
    )
