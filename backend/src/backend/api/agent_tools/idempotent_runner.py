"""상태 변경 Agent Tool API 의 멱등성 오케스트레이션 공통 헬퍼(계약 24.5).

Prepare / Auth Context 생성 / Execute 라우터가 공유한다:

    선점(begin) → 실제 처리(handler) → 결과 저장(complete)

같은 키로 이미 완료된 요청이면 handler 를 호출하지 않고 최초 응답을 그대로 복원한다.

utils/ 가 아니라 api/ 아래에 두는 이유: 응답 envelope 조립과 상태코드 결정은 API 계층의
책임이고, utils/ 는 services 에 의존하지 않는 leaf 로 유지하기 위함이다.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...schemas.execution_context import ResolvedExecutionContext
from ...schemas.response import CommonResponse
from ...services import idempotency_service
from ...utils.agent_response import agent_success_response


async def run_idempotent(
    session: AsyncSession,
    context: ResolvedExecutionContext,
    operation: str,
    raw_key: str | None,
    payload: BaseModel,
    message: str,
    handler: Callable[[], Awaitable[BaseModel]],
    success_status: int = 200,
) -> Response | CommonResponse:
    """멱등성 경계 안에서 handler 를 1회만 실행하고 결과를 저장·복원한다.

    success_status 는 최초 성공 응답의 상태코드다(예: Auth Context 생성은 201).
    복원 시에도 최초 상태코드를 그대로 돌려준다.
    """
    key = idempotency_service.require_key(raw_key)
    request_hash = idempotency_service.compute_request_hash(
        payload.model_dump(mode="json")
    )
    replay = await idempotency_service.begin(
        session, context, operation, key, request_hash
    )
    if replay is not None:
        return replay.to_response()

    data = await handler()
    response = agent_success_response(message=message, data=data)
    body = response.model_dump(mode="json", exclude_none=True)
    await idempotency_service.complete(
        session, context, operation, key, success_status, body
    )
    return response
