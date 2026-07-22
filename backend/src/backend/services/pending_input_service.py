"""일반 입력 대기(pending_input) 등록·소비 비즈니스 로직(UI-HITL 계약 1.3·1.5).

api(chat_api)와 webhook(webhook_api)은 얇게 두고, 대기 등록·검증·소비는 여기서 한다.
DB 접근은 repository 로 위임한다(계층 경계).

검증 실패는 Agent 를 재개하지 않고 같은 UI 에서 처리하도록(계약 1.5·8) FE 대면 채팅
엔드포인트 컨벤션에 맞춰 `HTTPException` 으로 던진다(/agent-tools/* 의 AgentToolError
와 구분). 존재 여부를 노출하지 않도록 미존재·타 세션은 같은 404 로 응답한다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.pending_input import PENDING_INPUT_STATUS_ACTIVE, PendingInput
from ..repository.pending_input_repository import (
    cancel_active_pending_inputs,
    create_pending_input,
    get_pending_input_by_request_id,
    mark_pending_input_consumed,
)

# 입력 대기 만료(초). 작동 검증 후 설정/Redis TTL 로 이전 가능(C4·C5).
PENDING_INPUT_TTL_SECONDS = 600


async def register_pending_input(
    session: AsyncSession,
    chat_session_id: UUID,
    input_request_id: str,
    ui_contract_id: str,
    ui_type: str,
    execution_context_id: UUID | None = None,
    agent_thread_id: str | None = None,
    ttl_seconds: int | None = None,
) -> PendingInput:
    """새 입력 대기를 등록한다.

    계약 1.3(세션당 활성 대기 1개)을 위해 기존 활성 대기를 먼저 무효화한다.
    """
    await cancel_active_pending_inputs(session, chat_session_id)
    ttl = ttl_seconds if ttl_seconds is not None else PENDING_INPUT_TTL_SECONDS
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
    return await create_pending_input(
        session,
        input_request_id=input_request_id,
        chat_session_id=chat_session_id,
        ui_contract_id=ui_contract_id,
        ui_type=ui_type,
        expires_at=expires_at,
        execution_context_id=execution_context_id,
        agent_thread_id=agent_thread_id,
    )


async def register_pending_input_from_event(
    session: AsyncSession,
    chat_session_id: UUID,
    metadata: dict | None,
    execution_context_id: UUID | None = None,
) -> PendingInput | None:
    """need_input Webhook metadata 에서 대기 정보를 추출해 등록한다(계약 1.4).

    metadata 는 `input_request_id`, `ui_contract_id`, `ui.{type,payload}` 를 담는다.
    필수 필드가 없으면(잘못된 need_input) 등록하지 않고 None 을 반환한다.
    실 Agent(Webhook)와 mock 드라이버가 공유하는 대기 영속 진입점이다.
    """
    metadata = metadata or {}
    input_request_id = metadata.get("input_request_id")
    ui_contract_id = metadata.get("ui_contract_id")
    ui = metadata.get("ui") or {}
    ui_type = ui.get("type")
    if not (input_request_id and ui_contract_id and ui_type):
        return None
    return await register_pending_input(
        session,
        chat_session_id=chat_session_id,
        input_request_id=str(input_request_id),
        ui_contract_id=str(ui_contract_id),
        ui_type=str(ui_type),
        execution_context_id=execution_context_id,
    )


async def consume_pending_input(
    session: AsyncSession,
    chat_session_id: UUID,
    input_request_id: str,
    now: datetime | None = None,
) -> PendingInput:
    """제출된 입력 요청을 검증하고 소비한다.

    - 미존재 / 다른 chat_session: 404 (존재 여부 비노출)
    - 만료: 410
    - 이미 소비·취소(비활성): 409
    - 활성·미만료: active→consumed 원자적 소비 후 반환(동시 제출은 409)
    """
    now = now or datetime.now(timezone.utc)
    pending = await get_pending_input_by_request_id(session, input_request_id)
    if pending is None or pending.chat_session_id != chat_session_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="대기 중인 입력 요청을 찾을 수 없습니다.",
        )
    if pending.expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="입력 요청이 만료되었습니다. 다시 시도해 주세요.",
        )
    if pending.status != PENDING_INPUT_STATUS_ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 처리된 입력 요청입니다.",
        )
    if not await mark_pending_input_consumed(session, pending, now):
        # 동시 제출로 다른 요청이 방금 소비함.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 처리된 입력 요청입니다.",
        )
    return pending
