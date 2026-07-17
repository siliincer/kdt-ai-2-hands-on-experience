"""추가 인증 Context 생명주기 검증(계약 15·16장).

repository 를 monkeypatch 해 DB 없이 생성 재사용/Execute 직전 재검증을 확인한다.
핵심: 만료는 오류가 아니라 재인증 신호(None)이고, 불일치·미검증은 AUTH_REQUIRED 다.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.agent_exceptions import AgentToolError
from backend.models.auth_context import AuthContextStatus
from backend.models.confirmation import Confirmation
from backend.schemas.execution_context import ResolvedExecutionContext
from backend.services import auth_context_service

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


def _confirmation(user_id) -> Confirmation:
    # 서비스는 id/user_id 만 사용하므로 가짜 객체로 충분하다(타입만 맞춰 준다).
    return cast(Confirmation, SimpleNamespace(id=uuid4(), user_id=user_id))


def _auth(
    user_id,
    confirmation_id,
    status=AuthContextStatus.VERIFIED,
    expires_in=180,
):
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        confirmation_id=confirmation_id,
        status=status,
        available_methods=["biometric", "password"],
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
    )


# ── 생성 (#7) ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_makes_new_when_none_active(monkeypatch):
    ctx = _ctx()
    conf = _confirmation(ctx.user_id)
    created = {}

    async def _get_active(session, confirmation_id, now):
        return None

    async def _create(session, **kwargs):
        created.update(kwargs)
        return _auth(ctx.user_id, conf.id, AuthContextStatus.PENDING)

    monkeypatch.setattr(auth_context_service, "get_active_auth_context", _get_active)
    monkeypatch.setattr(auth_context_service, "create_auth_context", _create)

    await auth_context_service.create_for_confirmation(_NO_SESSION, ctx, conf)

    assert created["confirmation_id"] == conf.id
    assert created["user_id"] == ctx.user_id
    assert created["available_methods"] == ["biometric", "password"]
    assert created["expires_at"] > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_create_reuses_active_context(monkeypatch):
    """같은 Confirmation 의 활성 인증 시도는 중복 생성하지 않는다(계약 15.4)."""
    ctx = _ctx()
    conf = _confirmation(ctx.user_id)
    existing = _auth(ctx.user_id, conf.id, AuthContextStatus.PENDING)
    calls = {"created": 0}

    async def _get_active(session, confirmation_id, now):
        return existing

    async def _create(session, **kwargs):
        calls["created"] += 1
        return existing

    monkeypatch.setattr(auth_context_service, "get_active_auth_context", _get_active)
    monkeypatch.setattr(auth_context_service, "create_auth_context", _create)

    result = await auth_context_service.create_for_confirmation(_NO_SESSION, ctx, conf)

    assert result is existing
    assert calls["created"] == 0


# ── Execute 직전 재검증 (#10 / #8) ───────────────────────────────────────────


def _patch_get(monkeypatch, auth_context):
    async def _get(session, auth_context_id):
        return auth_context

    monkeypatch.setattr(auth_context_service, "get_auth_context_by_id", _get)


@pytest.mark.asyncio
async def test_verified_auth_loads(monkeypatch):
    ctx = _ctx()
    conf = _confirmation(ctx.user_id)
    auth = _auth(ctx.user_id, conf.id, AuthContextStatus.VERIFIED)
    _patch_get(monkeypatch, auth)

    loaded = await auth_context_service.load_verified(
        _NO_SESSION, ctx, str(auth.id), conf
    )
    assert loaded is auth


@pytest.mark.asyncio
async def test_expired_status_signals_reauth(monkeypatch):
    """만료는 예외가 아니라 None(=재인증 필요) 이다(계약 16.5)."""
    ctx = _ctx()
    conf = _confirmation(ctx.user_id)
    _patch_get(monkeypatch, _auth(ctx.user_id, conf.id, AuthContextStatus.EXPIRED))

    result = await auth_context_service.load_verified(
        _NO_SESSION, ctx, str(uuid4()), conf
    )
    assert result is None


@pytest.mark.asyncio
async def test_past_expiry_signals_reauth(monkeypatch):
    ctx = _ctx()
    conf = _confirmation(ctx.user_id)
    _patch_get(
        monkeypatch,
        _auth(ctx.user_id, conf.id, AuthContextStatus.VERIFIED, expires_in=-1),
    )

    result = await auth_context_service.load_verified(
        _NO_SESSION, ctx, str(uuid4()), conf
    )
    assert result is None


@pytest.mark.asyncio
async def test_pending_auth_requires_authentication(monkeypatch):
    ctx = _ctx()
    conf = _confirmation(ctx.user_id)
    _patch_get(monkeypatch, _auth(ctx.user_id, conf.id, AuthContextStatus.PENDING))

    with pytest.raises(AgentToolError) as exc:
        await auth_context_service.load_verified(_NO_SESSION, ctx, str(uuid4()), conf)
    assert exc.value.status_code == 409
    assert exc.value.code == "AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_failed_auth_requires_authentication(monkeypatch):
    ctx = _ctx()
    conf = _confirmation(ctx.user_id)
    _patch_get(monkeypatch, _auth(ctx.user_id, conf.id, AuthContextStatus.FAILED))

    with pytest.raises(AgentToolError) as exc:
        await auth_context_service.load_verified(_NO_SESSION, ctx, str(uuid4()), conf)
    assert exc.value.code == "AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_other_users_auth_rejected(monkeypatch):
    ctx = _ctx()
    conf = _confirmation(ctx.user_id)
    _patch_get(monkeypatch, _auth(uuid4(), conf.id))  # 다른 사용자

    with pytest.raises(AgentToolError) as exc:
        await auth_context_service.load_verified(_NO_SESSION, ctx, str(uuid4()), conf)
    assert exc.value.code == "AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_auth_for_other_confirmation_rejected(monkeypatch):
    ctx = _ctx()
    conf = _confirmation(ctx.user_id)
    _patch_get(monkeypatch, _auth(ctx.user_id, uuid4()))  # 다른 Confirmation

    with pytest.raises(AgentToolError) as exc:
        await auth_context_service.load_verified(_NO_SESSION, ctx, str(uuid4()), conf)
    assert exc.value.code == "AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_missing_auth_rejected(monkeypatch):
    ctx = _ctx()
    _patch_get(monkeypatch, None)

    with pytest.raises(AgentToolError) as exc:
        await auth_context_service.load_verified(
            _NO_SESSION, ctx, str(uuid4()), _confirmation(ctx.user_id)
        )
    assert exc.value.code == "AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_malformed_auth_id_rejected():
    ctx = _ctx()
    with pytest.raises(AgentToolError) as exc:
        await auth_context_service.load_verified(
            _NO_SESSION, ctx, "not-a-uuid", _confirmation(ctx.user_id)
        )
    assert exc.value.code == "AUTH_REQUIRED"
