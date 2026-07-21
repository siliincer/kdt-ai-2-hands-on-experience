"""추가 인증 Context 생성 검증 (#7, 계약 15장).

Confirmation 검증 → 인증 시도 생성 → 응답 매핑을 DB 없이 확인한다.
설정 변경 Confirmation 으로는 인증을 만들 수 없어야 한다(계약 19.3).
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.agent_exceptions import AgentToolError
from backend.models.auth_context import AuthContextStatus
from backend.models.confirmation import ConfirmationOperation, ConfirmationStatus
from backend.schemas.agent_tools.auth_context import AuthContextCreateRequest
from backend.schemas.execution_context import ResolvedExecutionContext
from backend.services import confirmation_service
from backend.services.agent_tools import auth_tool_service

_NO_SESSION = cast(AsyncSession, None)


def _ctx(user_id=None) -> ResolvedExecutionContext:
    return ResolvedExecutionContext(
        execution_context_id=uuid4(),
        user_id=user_id or uuid4(),
        chat_session_id=uuid4(),
        agent_thread_id="thread_1",
        scopes=["transfer:request"],
        timezone="Asia/Seoul",
    )


def _confirmation(
    user_id,
    operation=ConfirmationOperation.INTERNAL_TRANSFER,
    status=ConfirmationStatus.APPROVED,
    expires_in=300,
):
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        operation=operation,
        status=status,
        fixed_data={"amount": 100_000},
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
    )


def _auth(confirmation_id, user_id, expires_in=180):
    return SimpleNamespace(
        id=uuid4(),
        confirmation_id=confirmation_id,
        user_id=user_id,
        status=AuthContextStatus.PENDING,
        available_methods=["biometric", "password"],
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
    )


@pytest.fixture(autouse=True)
def _silence_audit(monkeypatch):
    async def _record(session, context, **kwargs):
        return None

    monkeypatch.setattr(auth_tool_service.financial_audit_service, "record", _record)


def _patch_confirmation_lookup(monkeypatch, confirmation):
    """confirmation_service 가 실제 검증을 수행하도록 repository 만 대체한다."""

    async def _get(session, confirmation_id):
        return confirmation

    monkeypatch.setattr(confirmation_service, "get_confirmation_by_id", _get)


def _patch_auth_create(monkeypatch, auth_context):
    async def _create(session, context, confirmation):
        return auth_context

    monkeypatch.setattr(
        auth_tool_service.auth_context_service, "create_for_confirmation", _create
    )


@pytest.mark.asyncio
async def test_create_returns_authentication_required(monkeypatch):
    ctx = _ctx()
    conf = _confirmation(ctx.user_id)
    auth = _auth(conf.id, ctx.user_id)
    _patch_confirmation_lookup(monkeypatch, conf)
    _patch_auth_create(monkeypatch, auth)

    data = await auth_tool_service.create_auth_context(
        _NO_SESSION, ctx, AuthContextCreateRequest(confirmation_id=str(conf.id))
    )

    assert data.outcome == "authentication_required"
    assert data.auth_context_id == str(auth.id)
    view = data.auth_request_view
    assert view.available_methods == ["biometric", "password"]
    assert view.expires_at == auth.expires_at
    assert view.title


@pytest.mark.asyncio
async def test_external_transfer_confirmation_allowed(monkeypatch):
    ctx = _ctx()
    conf = _confirmation(ctx.user_id, ConfirmationOperation.EXTERNAL_TRANSFER)
    _patch_confirmation_lookup(monkeypatch, conf)
    _patch_auth_create(monkeypatch, _auth(conf.id, ctx.user_id))

    data = await auth_tool_service.create_auth_context(
        _NO_SESSION, ctx, AuthContextCreateRequest(confirmation_id=str(conf.id))
    )
    assert data.outcome == "authentication_required"


@pytest.mark.asyncio
async def test_setting_confirmation_rejected(monkeypatch):
    """설정 변경은 추가 인증 대상이 아니다(계약 19.3)."""
    ctx = _ctx()
    conf = _confirmation(ctx.user_id, ConfirmationOperation.DEFAULT_ACCOUNT_CHANGE)
    _patch_confirmation_lookup(monkeypatch, conf)

    with pytest.raises(AgentToolError) as exc:
        await auth_tool_service.create_auth_context(
            _NO_SESSION, ctx, AuthContextCreateRequest(confirmation_id=str(conf.id))
        )
    assert exc.value.code == "CONFIRMATION_MISMATCH"


@pytest.mark.asyncio
async def test_unapproved_confirmation_rejected(monkeypatch):
    ctx = _ctx()
    conf = _confirmation(ctx.user_id, status=ConfirmationStatus.PENDING)
    _patch_confirmation_lookup(monkeypatch, conf)

    with pytest.raises(AgentToolError) as exc:
        await auth_tool_service.create_auth_context(
            _NO_SESSION, ctx, AuthContextCreateRequest(confirmation_id=str(conf.id))
        )
    assert exc.value.code == "CONFIRMATION_REQUIRED"


@pytest.mark.asyncio
async def test_expired_confirmation_rejected(monkeypatch):
    ctx = _ctx()
    conf = _confirmation(ctx.user_id, expires_in=-1)
    _patch_confirmation_lookup(monkeypatch, conf)

    with pytest.raises(AgentToolError) as exc:
        await auth_tool_service.create_auth_context(
            _NO_SESSION, ctx, AuthContextCreateRequest(confirmation_id=str(conf.id))
        )
    assert exc.value.status_code == 410
    assert exc.value.code == "CONFIRMATION_EXPIRED"


@pytest.mark.asyncio
async def test_other_users_confirmation_rejected(monkeypatch):
    _patch_confirmation_lookup(monkeypatch, _confirmation(uuid4()))

    with pytest.raises(AgentToolError) as exc:
        await auth_tool_service.create_auth_context(
            _NO_SESSION, _ctx(), AuthContextCreateRequest(confirmation_id=str(uuid4()))
        )
    assert exc.value.code == "CONFIRMATION_MISMATCH"


# ── 라우터 게이트 ────────────────────────────────────────────────────────────


def test_auth_contexts_requires_service_token(client):
    response = client.post(
        "/api/v1/agent-tools/auth-contexts", json={"confirmation_id": str(uuid4())}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_SERVICE_TOKEN"
