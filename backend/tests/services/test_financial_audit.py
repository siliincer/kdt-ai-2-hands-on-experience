"""금융 감사 로그 기록 검증(계약 25장).

실행 Context 에서 주체 정보(user/session/thread/context)가 자동으로 채워지는지 확인한다.
"""

from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.financial_audit_log import (
    EVENT_CONFIRMATION_CREATED,
    EVENT_SETTING_CHANGE_COMPLETED,
)
from backend.schemas.execution_context import ResolvedExecutionContext
from backend.services import financial_audit_service

_NO_SESSION = cast(AsyncSession, None)


def _ctx() -> ResolvedExecutionContext:
    return ResolvedExecutionContext(
        execution_context_id=uuid4(),
        user_id=uuid4(),
        chat_session_id=uuid4(),
        agent_thread_id="thread_1",
        scopes=["settings:write"],
        timezone="Asia/Seoul",
    )


@pytest.fixture
def captured(monkeypatch):
    box = {}

    async def _create(session, **kwargs):
        box.update(kwargs)
        return object()

    monkeypatch.setattr(financial_audit_service, "create_financial_audit_log", _create)
    return box


@pytest.mark.asyncio
async def test_context_fields_are_filled(captured):
    ctx = _ctx()

    await financial_audit_service.record(
        _NO_SESSION,
        ctx,
        event_type=EVENT_CONFIRMATION_CREATED,
        operation="default_account_prepare",
        outcome="ready_for_confirmation",
    )

    assert captured["user_id"] == ctx.user_id
    assert captured["execution_context_id"] == ctx.execution_context_id
    assert captured["chat_session_id"] == ctx.chat_session_id
    assert captured["agent_thread_id"] == "thread_1"
    assert captured["actor_type"] == "agent_service"
    assert captured["event_type"] == EVENT_CONFIRMATION_CREATED
    assert captured["outcome"] == "ready_for_confirmation"


@pytest.mark.asyncio
async def test_business_fields_are_passed_through(captured):
    confirmation_id = uuid4()

    await financial_audit_service.record(
        _NO_SESSION,
        _ctx(),
        event_type=EVENT_SETTING_CHANGE_COMPLETED,
        operation="default_account_execute",
        outcome="completed",
        contract_id="API-DEFAULT-ACCOUNT-EXECUTE",
        confirmation_id=confirmation_id,
        idempotency_key="default_account_execute:confirm-1",
        reason=None,
        policy_codes=[],
    )

    assert captured["contract_id"] == "API-DEFAULT-ACCOUNT-EXECUTE"
    assert captured["confirmation_id"] == confirmation_id
    assert captured["idempotency_key"] == "default_account_execute:confirm-1"
    assert captured["policy_codes"] == []
