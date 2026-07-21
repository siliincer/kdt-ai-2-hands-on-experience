"""멱등성 처리 검증(계약 24장).

repository 를 monkeypatch 해 DB 없이 선점/복원/충돌/처리중 분기를 확인한다.
"""

from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.agent_exceptions import AgentToolError
from backend.models.idempotency_key import IdempotencyStatus
from backend.schemas.execution_context import ResolvedExecutionContext
from backend.services import idempotency_service

_NO_SESSION = cast(AsyncSession, None)
_OP = "default_account_execute"


def _ctx() -> ResolvedExecutionContext:
    return ResolvedExecutionContext(
        execution_context_id=uuid4(),
        user_id=uuid4(),
        chat_session_id=uuid4(),
        agent_thread_id="thread_1",
        scopes=["settings:write"],
        timezone="Asia/Seoul",
    )


def _record(request_hash, status=IdempotencyStatus.COMPLETED, body=None, code=200):
    return SimpleNamespace(
        id=uuid4(),
        request_hash=request_hash,
        status=status,
        response_status=code,
        response_body=body,
    )


def _patch(monkeypatch, existing, created=None):
    async def _get(session, ctx_id, operation, key):
        return existing

    async def _create(session, **kwargs):
        return created or SimpleNamespace(id=uuid4())

    monkeypatch.setattr(idempotency_service, "get_idempotency_record", _get)
    monkeypatch.setattr(idempotency_service, "create_in_progress", _create)


# ── request hash ─────────────────────────────────────────────────────────────


def test_hash_is_key_order_independent():
    a = idempotency_service.compute_request_hash({"b": 2, "a": 1})
    b = idempotency_service.compute_request_hash({"a": 1, "b": 2})
    assert a == b


def test_hash_differs_on_value_change():
    a = idempotency_service.compute_request_hash({"amount": 1000})
    b = idempotency_service.compute_request_hash({"amount": 2000})
    assert a != b


# ── require_key ──────────────────────────────────────────────────────────────


def test_missing_key_rejected():
    for value in (None, "", "   "):
        with pytest.raises(AgentToolError) as exc:
            idempotency_service.require_key(value)
        assert exc.value.code == "INVALID_REQUEST"


def test_key_is_trimmed():
    assert idempotency_service.require_key("  k-1 ") == "k-1"


# ── begin ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_first_call_reserves_and_proceeds(monkeypatch):
    _patch(monkeypatch, existing=None)

    replay = await idempotency_service.begin(_NO_SESSION, _ctx(), _OP, "k-1", "hash-1")

    assert replay is None  # 선점만 하고 실제 처리로 진행


@pytest.mark.asyncio
async def test_concurrent_insert_conflict_maps_to_in_progress(monkeypatch):
    """C1: 같은 순간 다른 요청이 같은 키를 선점(IntegrityError) → 처리중(409)."""
    from sqlalchemy.exc import IntegrityError

    async def _get(session, ctx_id, operation, key):
        return None  # 조회 시점엔 없음

    async def _create(session, **kwargs):
        raise IntegrityError("insert", {}, Exception("unique violation"))

    monkeypatch.setattr(idempotency_service, "get_idempotency_record", _get)
    monkeypatch.setattr(idempotency_service, "create_in_progress", _create)

    with pytest.raises(AgentToolError) as exc:
        await idempotency_service.begin(_NO_SESSION, _ctx(), _OP, "k-1", "hash-1")
    assert exc.value.status_code == 409
    assert exc.value.code == "IDEMPOTENCY_REQUEST_IN_PROGRESS"
    assert exc.value.headers == {"Retry-After": "1"}


@pytest.mark.asyncio
async def test_same_key_same_body_replays_first_response(monkeypatch):
    body = {"success": True, "data": {"outcome": "completed"}}
    _patch(monkeypatch, existing=_record("hash-1", body=body, code=200))

    replay = await idempotency_service.begin(_NO_SESSION, _ctx(), _OP, "k-1", "hash-1")

    assert replay is not None
    assert replay.status_code == 200
    assert replay.body == body


@pytest.mark.asyncio
async def test_same_key_different_body_conflicts(monkeypatch):
    _patch(monkeypatch, existing=_record("hash-1"))

    with pytest.raises(AgentToolError) as exc:
        await idempotency_service.begin(_NO_SESSION, _ctx(), _OP, "k-1", "hash-2")
    assert exc.value.status_code == 409
    assert exc.value.code == "IDEMPOTENCY_KEY_CONFLICT"


@pytest.mark.asyncio
async def test_in_progress_returns_retry_after(monkeypatch):
    _patch(monkeypatch, existing=_record("hash-1", IdempotencyStatus.IN_PROGRESS))

    with pytest.raises(AgentToolError) as exc:
        await idempotency_service.begin(_NO_SESSION, _ctx(), _OP, "k-1", "hash-1")
    assert exc.value.status_code == 409
    assert exc.value.code == "IDEMPOTENCY_REQUEST_IN_PROGRESS"
    assert exc.value.headers == {"Retry-After": "1"}
    assert exc.value.retryable is True


# ── complete ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_complete_stores_response(monkeypatch):
    record = _record("hash-1", IdempotencyStatus.IN_PROGRESS)
    saved = {}

    async def _get(session, ctx_id, operation, key):
        return record

    async def _complete(session, rec, status, body):
        saved["status"] = status
        saved["body"] = body
        return rec

    monkeypatch.setattr(idempotency_service, "get_idempotency_record", _get)
    monkeypatch.setattr(idempotency_service, "complete_idempotency", _complete)

    body = {"success": True}
    await idempotency_service.complete(_NO_SESSION, _ctx(), _OP, "k-1", 200, body)

    assert saved == {"status": 200, "body": body}


@pytest.mark.asyncio
async def test_complete_without_record_is_noop(monkeypatch):
    async def _get(session, ctx_id, operation, key):
        return None

    monkeypatch.setattr(idempotency_service, "get_idempotency_record", _get)
    # 예외 없이 조용히 넘어가야 한다.
    await idempotency_service.complete(_NO_SESSION, _ctx(), _OP, "k-1", 200, {})


def test_replay_to_response_preserves_status_and_body():
    replay = idempotency_service.IdempotentReplay(200, {"success": True})
    response = replay.to_response()
    assert response.status_code == 200
