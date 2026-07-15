"""Execution Context 해석·검증(resolve_context) 단위 테스트.

DB 없이 repository 조회를 monkeypatch 로 대체해 검증 분기를 확인한다
(test_transfer_service 스타일). 만료·취소·형식오류의 계약 오류코드 매핑을 본다.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.agent_exceptions import AgentToolError
from backend.models.execution_context import ExecutionContextStatus
from backend.services import execution_context_service

_NO_SESSION = cast(AsyncSession, None)


def _fake_context(
    *,
    status=ExecutionContextStatus.ACTIVE,
    expires_in_seconds=600,
    scopes=None,
    agent_thread_id="thread_1",
    timezone_name="Asia/Seoul",
):
    return SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        chat_session_id=uuid4(),
        agent_thread_id=agent_thread_id,
        scopes=scopes if scopes is not None else ["account:read"],
        status=status,
        timezone=timezone_name,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds),
    )


def _patch_lookup(monkeypatch, context):
    async def _lookup(session, context_id):
        return context

    monkeypatch.setattr(
        execution_context_service, "get_execution_context_by_id", _lookup
    )


@pytest.mark.asyncio
async def test_active_context_resolves(monkeypatch):
    ctx = _fake_context(scopes=["account:read", "transfer:request"])
    _patch_lookup(monkeypatch, ctx)

    resolved = await execution_context_service.resolve_context(_NO_SESSION, str(ctx.id))

    assert resolved.execution_context_id == ctx.id
    assert resolved.user_id == ctx.user_id
    assert resolved.chat_session_id == ctx.chat_session_id
    assert resolved.agent_thread_id == "thread_1"
    assert resolved.timezone == "Asia/Seoul"
    assert resolved.has_scope("transfer:request") is True
    assert resolved.has_scope("settings:write") is False


@pytest.mark.asyncio
async def test_missing_context_raises_invalid(monkeypatch):
    _patch_lookup(monkeypatch, None)
    with pytest.raises(AgentToolError) as exc:
        await execution_context_service.resolve_context(_NO_SESSION, str(uuid4()))
    assert exc.value.status_code == 401
    assert exc.value.code == "INVALID_EXECUTION_CONTEXT"


@pytest.mark.asyncio
async def test_expired_status_raises_410(monkeypatch):
    _patch_lookup(monkeypatch, _fake_context(status=ExecutionContextStatus.EXPIRED))
    with pytest.raises(AgentToolError) as exc:
        await execution_context_service.resolve_context(_NO_SESSION, str(uuid4()))
    assert exc.value.status_code == 410
    assert exc.value.code == "EXECUTION_CONTEXT_EXPIRED"


@pytest.mark.asyncio
async def test_past_expiry_raises_410(monkeypatch):
    _patch_lookup(monkeypatch, _fake_context(expires_in_seconds=-1))
    with pytest.raises(AgentToolError) as exc:
        await execution_context_service.resolve_context(_NO_SESSION, str(uuid4()))
    assert exc.value.code == "EXECUTION_CONTEXT_EXPIRED"


@pytest.mark.asyncio
async def test_cancelled_status_raises_invalid(monkeypatch):
    _patch_lookup(monkeypatch, _fake_context(status=ExecutionContextStatus.CANCELLED))
    with pytest.raises(AgentToolError) as exc:
        await execution_context_service.resolve_context(_NO_SESSION, str(uuid4()))
    assert exc.value.status_code == 401
    assert exc.value.code == "INVALID_EXECUTION_CONTEXT"


@pytest.mark.asyncio
async def test_missing_header_raises_invalid():
    with pytest.raises(AgentToolError) as exc:
        await execution_context_service.resolve_context(_NO_SESSION, None)
    assert exc.value.code == "INVALID_EXECUTION_CONTEXT"


@pytest.mark.asyncio
async def test_malformed_id_raises_invalid():
    with pytest.raises(AgentToolError) as exc:
        await execution_context_service.resolve_context(_NO_SESSION, "not-a-uuid")
    assert exc.value.code == "INVALID_EXECUTION_CONTEXT"
