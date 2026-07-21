"""Confirmation 생명주기 검증(계약 14·19·21·23장).

repository 를 monkeypatch 해 DB 없이 Execute 직전 재검증 분기를 확인한다.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.agent_exceptions import AgentToolError
from backend.models.confirmation import ConfirmationOperation, ConfirmationStatus
from backend.schemas.execution_context import ResolvedExecutionContext
from backend.services import confirmation_service

_NO_SESSION = cast(AsyncSession, None)
_OP = ConfirmationOperation.DEFAULT_ACCOUNT_CHANGE


def _ctx(user_id=None) -> ResolvedExecutionContext:
    return ResolvedExecutionContext(
        execution_context_id=uuid4(),
        user_id=user_id or uuid4(),
        chat_session_id=uuid4(),
        agent_thread_id="thread_1",
        scopes=["settings:write"],
        timezone="Asia/Seoul",
    )


def _confirmation(
    user_id,
    status=ConfirmationStatus.APPROVED,
    operation=_OP,
    expires_in=300,
):
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        operation=operation,
        status=status,
        fixed_data={"account_id": "acc-1"},
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
    )


def _patch_get(monkeypatch, confirmation):
    async def _get(session, confirmation_id):
        return confirmation

    monkeypatch.setattr(confirmation_service, "get_confirmation_by_id", _get)


@pytest.mark.asyncio
async def test_approved_confirmation_loads(monkeypatch):
    ctx = _ctx()
    conf = _confirmation(ctx.user_id)
    _patch_get(monkeypatch, conf)

    loaded = await confirmation_service.load_for_execute(_NO_SESSION, ctx, str(conf.id), _OP)
    assert loaded.fixed_data == {"account_id": "acc-1"}


@pytest.mark.asyncio
async def test_pending_requires_approval(monkeypatch):
    ctx = _ctx()
    _patch_get(monkeypatch, _confirmation(ctx.user_id, ConfirmationStatus.PENDING))

    with pytest.raises(AgentToolError) as exc:
        await confirmation_service.load_for_execute(_NO_SESSION, ctx, str(uuid4()), _OP)
    assert exc.value.status_code == 409
    assert exc.value.code == "CONFIRMATION_REQUIRED"


@pytest.mark.asyncio
async def test_expired_status_rejected(monkeypatch):
    ctx = _ctx()
    _patch_get(monkeypatch, _confirmation(ctx.user_id, ConfirmationStatus.EXPIRED))

    with pytest.raises(AgentToolError) as exc:
        await confirmation_service.load_for_execute(_NO_SESSION, ctx, str(uuid4()), _OP)
    assert exc.value.status_code == 410
    assert exc.value.code == "CONFIRMATION_EXPIRED"


@pytest.mark.asyncio
async def test_past_expiry_rejected(monkeypatch):
    ctx = _ctx()
    _patch_get(monkeypatch, _confirmation(ctx.user_id, expires_in=-1))

    with pytest.raises(AgentToolError) as exc:
        await confirmation_service.load_for_execute(_NO_SESSION, ctx, str(uuid4()), _OP)
    assert exc.value.code == "CONFIRMATION_EXPIRED"


@pytest.mark.asyncio
async def test_other_users_confirmation_is_mismatch(monkeypatch):
    _patch_get(monkeypatch, _confirmation(uuid4()))  # 다른 사용자 소유

    with pytest.raises(AgentToolError) as exc:
        await confirmation_service.load_for_execute(_NO_SESSION, _ctx(), str(uuid4()), _OP)
    assert exc.value.status_code == 409
    assert exc.value.code == "CONFIRMATION_MISMATCH"


@pytest.mark.asyncio
async def test_operation_mismatch_rejected(monkeypatch):
    ctx = _ctx()
    _patch_get(
        monkeypatch,
        _confirmation(ctx.user_id, operation=ConfirmationOperation.EXTERNAL_TRANSFER),
    )

    with pytest.raises(AgentToolError) as exc:
        await confirmation_service.load_for_execute(_NO_SESSION, ctx, str(uuid4()), _OP)
    assert exc.value.code == "CONFIRMATION_MISMATCH"


@pytest.mark.asyncio
async def test_already_executed_rejected(monkeypatch):
    ctx = _ctx()
    _patch_get(monkeypatch, _confirmation(ctx.user_id, ConfirmationStatus.EXECUTED))

    with pytest.raises(AgentToolError) as exc:
        await confirmation_service.load_for_execute(_NO_SESSION, ctx, str(uuid4()), _OP)
    assert exc.value.code == "CONFIRMATION_MISMATCH"


@pytest.mark.asyncio
async def test_invalidated_rejected(monkeypatch):
    ctx = _ctx()
    _patch_get(monkeypatch, _confirmation(ctx.user_id, ConfirmationStatus.INVALIDATED))

    with pytest.raises(AgentToolError) as exc:
        await confirmation_service.load_for_execute(_NO_SESSION, ctx, str(uuid4()), _OP)
    assert exc.value.code == "CONFIRMATION_MISMATCH"


@pytest.mark.asyncio
async def test_missing_confirmation_is_mismatch(monkeypatch):
    _patch_get(monkeypatch, None)

    with pytest.raises(AgentToolError) as exc:
        await confirmation_service.load_for_execute(_NO_SESSION, _ctx(), str(uuid4()), _OP)
    assert exc.value.code == "CONFIRMATION_MISMATCH"


@pytest.mark.asyncio
async def test_malformed_id_is_mismatch():
    with pytest.raises(AgentToolError) as exc:
        await confirmation_service.load_for_execute(_NO_SESSION, _ctx(), "not-a-uuid", _OP)
    assert exc.value.code == "CONFIRMATION_MISMATCH"
