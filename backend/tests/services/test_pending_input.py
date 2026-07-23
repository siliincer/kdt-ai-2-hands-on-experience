"""일반 입력 대기(pending_input) 등록·소비 검증(UI-HITL 계약 1.3·1.5).

repository 를 monkeypatch 해 DB 없이 등록 시 활성 무효화와 소비 검증(만료·비활성·타
세션)을 확인한다. 검증 실패는 Agent 를 재개하지 않으므로 HTTPException 으로 던진다.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.pending_input import (
    PENDING_INPUT_STATUS_ACTIVE,
    PENDING_INPUT_STATUS_CONSUMED,
)
from backend.services import pending_input_service

_NO_SESSION = cast(AsyncSession, None)


def _pending(
    chat_session_id,
    input_request_id="input_1",
    status=PENDING_INPUT_STATUS_ACTIVE,
    expires_in=600,
):
    return SimpleNamespace(
        id=uuid4(),
        input_request_id=input_request_id,
        chat_session_id=chat_session_id,
        status=status,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
    )


# ── 등록 ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_cancels_prior_active_then_creates(monkeypatch):
    """새 대기 등록 전에 기존 활성 대기를 무효화한다(계약 1.3)."""
    chat_session_id = uuid4()
    calls = {"cancelled": 0, "created": None}

    async def _cancel(session, cid):
        calls["cancelled"] += 1
        return 1

    async def _create(session, **kwargs):
        calls["created"] = kwargs
        return _pending(chat_session_id, kwargs["input_request_id"])

    monkeypatch.setattr(pending_input_service, "cancel_active_pending_inputs", _cancel)
    monkeypatch.setattr(pending_input_service, "create_pending_input", _create)

    await pending_input_service.register_pending_input(
        _NO_SESSION,
        chat_session_id=chat_session_id,
        input_request_id="input_amount_1",
        ui_contract_id="UI-TRANSFER-AMOUNT-INPUT",
        ui_type="number_input",
    )

    assert calls["cancelled"] == 1
    created = calls["created"]
    assert created["input_request_id"] == "input_amount_1"
    assert created["ui_contract_id"] == "UI-TRANSFER-AMOUNT-INPUT"
    assert created["ui_type"] == "number_input"
    assert created["expires_at"] > datetime.now(timezone.utc)


# ── 소비 ─────────────────────────────────────────────────────────────────────


def _patch_get(monkeypatch, pending):
    async def _get(session, input_request_id):
        return pending

    monkeypatch.setattr(pending_input_service, "get_pending_input_by_request_id", _get)


def _patch_consume(monkeypatch, ok=True):
    async def _consume(session, pending, now):
        pending.status = PENDING_INPUT_STATUS_CONSUMED
        return ok

    monkeypatch.setattr(pending_input_service, "mark_pending_input_consumed", _consume)


@pytest.mark.asyncio
async def test_consume_active_succeeds(monkeypatch):
    chat_session_id = uuid4()
    pending = _pending(chat_session_id, "input_1")
    _patch_get(monkeypatch, pending)
    _patch_consume(monkeypatch, ok=True)

    result = await pending_input_service.consume_pending_input(_NO_SESSION, chat_session_id, "input_1")
    assert result is pending
    assert result.status == PENDING_INPUT_STATUS_CONSUMED


@pytest.mark.asyncio
async def test_consume_missing_is_404(monkeypatch):
    _patch_get(monkeypatch, None)
    with pytest.raises(HTTPException) as exc:
        await pending_input_service.consume_pending_input(_NO_SESSION, uuid4(), "input_x")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_consume_other_session_is_404(monkeypatch):
    """타 세션 대기는 존재 여부를 노출하지 않도록 같은 404 로 응답한다."""
    pending = _pending(uuid4(), "input_1")  # 다른 chat_session
    _patch_get(monkeypatch, pending)
    with pytest.raises(HTTPException) as exc:
        await pending_input_service.consume_pending_input(_NO_SESSION, uuid4(), "input_1")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_consume_expired_is_410(monkeypatch):
    chat_session_id = uuid4()
    _patch_get(monkeypatch, _pending(chat_session_id, "input_1", expires_in=-1))
    with pytest.raises(HTTPException) as exc:
        await pending_input_service.consume_pending_input(_NO_SESSION, chat_session_id, "input_1")
    assert exc.value.status_code == 410


@pytest.mark.asyncio
async def test_consume_inactive_is_409(monkeypatch):
    chat_session_id = uuid4()
    _patch_get(
        monkeypatch,
        _pending(chat_session_id, "input_1", status=PENDING_INPUT_STATUS_CONSUMED),
    )
    with pytest.raises(HTTPException) as exc:
        await pending_input_service.consume_pending_input(_NO_SESSION, chat_session_id, "input_1")
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_consume_race_lost_is_409(monkeypatch):
    """동시 제출로 소비 UPDATE 가 0행이면 409."""
    chat_session_id = uuid4()
    _patch_get(monkeypatch, _pending(chat_session_id, "input_1"))
    _patch_consume(monkeypatch, ok=False)
    with pytest.raises(HTTPException) as exc:
        await pending_input_service.consume_pending_input(_NO_SESSION, chat_session_id, "input_1")
    assert exc.value.status_code == 409
