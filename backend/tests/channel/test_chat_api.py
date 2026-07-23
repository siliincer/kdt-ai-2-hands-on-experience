from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.models.auth_context import AuthContextStatus
from backend.models.confirmation import ConfirmationStatus
from backend.services import chat_service, chat_session_service

# 실 Agent 연동(agent_client)으로 mock_agent_driver 는 런타임에서 제거됐다. 이 파일은
# Backend 오케스트레이션(세션 확정·재개 전 검증·인증)의 실제 경로만 검증한다. mock 드라이버의
# 인텐트/뷰빌더 순수 함수 테스트는 계약이 실 Agent 로 넘어가면서 정리됐다.


# --- chat_session_service (repository 를 모킹) --------------------------------


@pytest.mark.asyncio
async def test_resolve_chat_session_returns_given_id_when_owner():
    user_id, chat_session_id = uuid4(), uuid4()
    session = AsyncMock()
    with patch.object(
        chat_session_service,
        "get_chat_session",
        AsyncMock(return_value=SimpleNamespace(id=chat_session_id)),
    ):
        result = await chat_session_service.resolve_chat_session(session, user_id, chat_session_id)
    assert result == chat_session_id


@pytest.mark.asyncio
async def test_resolve_chat_session_creates_when_missing():
    user_id, new_id = uuid4(), uuid4()
    session = AsyncMock()
    with patch.object(
        chat_session_service,
        "create_chat_session",
        AsyncMock(return_value=SimpleNamespace(id=new_id)),
    ):
        result = await chat_session_service.resolve_chat_session(session, user_id, None)
    assert result == new_id


@pytest.mark.asyncio
async def test_verify_owner_raises_404_when_not_found():
    session = AsyncMock()
    with patch.object(chat_session_service, "get_chat_session", AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as exc:
            await chat_session_service.verify_chat_session_owner(session, uuid4(), uuid4())
    assert exc.value.status_code == 404


# --- 라우트 존재 + 인증 ------------------------------------------------------


def test_chat_requires_auth(client: TestClient):
    response = client.post("/api/v1/chat", json={"message": "안녕"})
    assert response.status_code == 401


def test_approve_requires_auth(client: TestClient):
    response = client.post(
        "/api/v1/agent/approve",
        json={
            "chat_session_id": str(uuid4()),
            "approval_id": "x",
            "decision": "approve",
        },
    )
    assert response.status_code == 401


def test_agent_input_requires_auth(client: TestClient):
    response = client.post(
        "/api/v1/agent/input",
        json={
            "chat_session_id": str(uuid4()),
            "input_request_id": "input_1",
            "value": {"account_selection_outcome": "selected", "account_ids": ["a"]},
        },
    )
    assert response.status_code == 401


def test_agent_authenticate_requires_auth(client: TestClient):
    response = client.post(
        "/api/v1/agent/authenticate",
        json={
            "chat_session_id": str(uuid4()),
            "auth_context_id": "auth_1",
            "password": "x",
        },
    )
    assert response.status_code == 401


# --- need_input Webhook → pending_input 등록 헬퍼 -----------------------------


@pytest.mark.asyncio
async def test_register_from_event_extracts_metadata():
    from backend.services import pending_input_service

    captured = {}

    async def _register(session, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(**kwargs)

    with patch.object(pending_input_service, "register_pending_input", _register):
        result = await pending_input_service.register_pending_input_from_event(
            AsyncMock(),
            chat_session_id=uuid4(),
            metadata={
                "input_request_id": "input_amount_1",
                "ui_contract_id": "UI-TRANSFER-AMOUNT-INPUT",
                "ui": {"type": "number_input", "payload": {"currency": "KRW"}},
            },
        )
    assert result is not None
    assert captured["input_request_id"] == "input_amount_1"
    assert captured["ui_contract_id"] == "UI-TRANSFER-AMOUNT-INPUT"
    assert captured["ui_type"] == "number_input"


@pytest.mark.asyncio
async def test_register_from_event_skips_when_incomplete():
    """input_request_id·ui_contract_id·ui.type 중 하나라도 없으면 등록하지 않는다."""
    from backend.services import pending_input_service

    called = {"n": 0}

    async def _register(session, **kwargs):
        called["n"] += 1

    with patch.object(pending_input_service, "register_pending_input", _register):
        result = await pending_input_service.register_pending_input_from_event(
            AsyncMock(),
            chat_session_id=uuid4(),
            metadata={"input_request_id": "input_1"},  # ui_contract_id/ui 없음
        )
    assert result is None
    assert called["n"] == 0


# --- 설정 confirm_modal → Confirmation 생명주기 검증(재개 전 검증 계약) ----------


def _confirmation(user_id, status=ConfirmationStatus.PENDING, expires_in=300) -> Any:
    # 실제 Confirmation ORM 대신 덕타이핑용 SimpleNamespace 를 반환한다(타입 검사 완화).
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        status=status,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        execution_context_id=uuid4(),
    )


@pytest.mark.asyncio
async def test_apply_confirmation_approve_marks_approved():
    calls = {"approve": 0, "invalidate": 0}

    async def _approve(session, c):
        calls["approve"] += 1

    async def _invalidate(session, c):
        calls["invalidate"] += 1

    with (
        patch.object(chat_service.confirmation_service, "approve", _approve),
        patch.object(chat_service.confirmation_service, "invalidate", _invalidate),
    ):
        await chat_service._apply_confirmation_decision(AsyncMock(), _confirmation(uuid4()), "approve")
    assert calls == {"approve": 1, "invalidate": 0}


@pytest.mark.asyncio
async def test_apply_confirmation_cancel_invalidates():
    calls = {"approve": 0, "invalidate": 0}

    async def _approve(session, c):
        calls["approve"] += 1

    async def _invalidate(session, c):
        calls["invalidate"] += 1

    with (
        patch.object(chat_service.confirmation_service, "approve", _approve),
        patch.object(chat_service.confirmation_service, "invalidate", _invalidate),
    ):
        await chat_service._apply_confirmation_decision(AsyncMock(), _confirmation(uuid4()), "cancelled")
    assert calls == {"approve": 0, "invalidate": 1}


@pytest.mark.asyncio
async def test_load_confirmation_other_user_is_404():
    conf = _confirmation(uuid4())  # 다른 사용자

    with patch.object(chat_service, "get_confirmation_by_id", AsyncMock(return_value=conf)):
        with pytest.raises(HTTPException) as exc:
            await chat_service._load_owned_confirmation(AsyncMock(), uuid4(), str(conf.id))
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_load_confirmation_expired_is_410():
    user_id = uuid4()
    conf = _confirmation(user_id, expires_in=-1)

    with patch.object(chat_service, "get_confirmation_by_id", AsyncMock(return_value=conf)):
        with pytest.raises(HTTPException) as exc:
            await chat_service._load_owned_confirmation(AsyncMock(), user_id, str(conf.id))
    assert exc.value.status_code == 410


@pytest.mark.asyncio
async def test_load_confirmation_non_pending_is_409():
    user_id = uuid4()
    conf = _confirmation(user_id, status=ConfirmationStatus.APPROVED)

    with patch.object(chat_service, "get_confirmation_by_id", AsyncMock(return_value=conf)):
        with pytest.raises(HTTPException) as exc:
            await chat_service._load_owned_confirmation(AsyncMock(), user_id, str(conf.id))
    assert exc.value.status_code == 409


# --- 추가 인증(authenticate_and_resume) → 검증 후 Agent 재개 -------------------


def _auth_context(user_id, status=AuthContextStatus.PENDING, expires_in=180):
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        status=status,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        confirmation_id=uuid4(),
    )


def _patch_auth(auth_context, password_ok):
    """authenticate_and_resume 의 의존성을 대체하는 패치 목록과 캡처를 만든다.

    재개는 실 Agent 클라이언트(resume_authentication)로 나가므로 stub 으로 잡아
    전달된 auth_status 를 캡처한다.
    """
    user = SimpleNamespace(password_hash="hash")
    calls = {"verified": 0, "failed": 0, "resumed": []}

    async def _owner(session, uid, cid):
        return None

    async def _resume_authentication(*, auth_status, **kwargs):
        calls["resumed"].append(auth_status)

    agent_stub = SimpleNamespace(resume_authentication=_resume_authentication)

    async def _mark_verified(session, ac):
        calls["verified"] += 1

    async def _set_status(session, ac, status, **kw):
        calls["failed"] += 1

    # auth_context → confirmation → execution_context(agent_thread_id) 해소 경로.
    confirmation = SimpleNamespace(execution_context_id=uuid4())
    context = SimpleNamespace(agent_thread_id="thread_abc")

    patches = [
        patch.object(chat_service, "verify_chat_session_owner", _owner),
        patch.object(chat_service, "get_auth_context_by_id", AsyncMock(return_value=auth_context)),
        patch.object(chat_service, "get_user_by_id", AsyncMock(return_value=user)),
        patch.object(chat_service, "verify_password", lambda p, h: password_ok),
        patch.object(chat_service.auth_context_service, "mark_verified", _mark_verified),
        patch.object(chat_service, "set_auth_context_status", _set_status),
        patch.object(chat_service, "get_confirmation_by_id", AsyncMock(return_value=confirmation)),
        patch.object(
            chat_service,
            "get_execution_context_by_id",
            AsyncMock(return_value=context),
        ),
        patch.object(chat_service, "get_agent_client", lambda: agent_stub),
    ]
    return patches, calls


@pytest.mark.asyncio
async def test_authenticate_correct_password_verifies():
    user_id = uuid4()
    auth = _auth_context(user_id)
    patches, calls = _patch_auth(auth, password_ok=True)
    for p in patches:
        p.start()
    try:
        result = await chat_service.authenticate_and_resume(AsyncMock(), user_id, uuid4(), str(auth.id), "a1b2c3d4!!")
    finally:
        for p in patches:
            p.stop()
    assert result == "verified"
    assert calls["verified"] == 1 and calls["resumed"] == ["verified"]


@pytest.mark.asyncio
async def test_authenticate_wrong_password_fails():
    user_id = uuid4()
    auth = _auth_context(user_id)
    patches, calls = _patch_auth(auth, password_ok=False)
    for p in patches:
        p.start()
    try:
        result = await chat_service.authenticate_and_resume(AsyncMock(), user_id, uuid4(), str(auth.id), "wrong")
    finally:
        for p in patches:
            p.stop()
    assert result == "failed"
    assert calls["failed"] == 1 and calls["resumed"] == ["failed"]


@pytest.mark.asyncio
async def test_authenticate_other_user_is_404():
    auth = _auth_context(uuid4())  # 다른 사용자
    patches, _ = _patch_auth(auth, password_ok=True)
    for p in patches:
        p.start()
    try:
        with pytest.raises(HTTPException) as exc:
            await chat_service.authenticate_and_resume(AsyncMock(), uuid4(), uuid4(), str(auth.id), "x")
    finally:
        for p in patches:
            p.stop()
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_authenticate_expired_is_410():
    user_id = uuid4()
    auth = _auth_context(user_id, expires_in=-1)
    patches, _ = _patch_auth(auth, password_ok=True)
    for p in patches:
        p.start()
    try:
        with pytest.raises(HTTPException) as exc:
            await chat_service.authenticate_and_resume(AsyncMock(), user_id, uuid4(), str(auth.id), "x")
    finally:
        for p in patches:
            p.stop()
    assert exc.value.status_code == 410


# --- 취소 시 Backend 종료 책임(계약점검 #6) ------------------------------------


def test_is_cancel_input_detects_any_outcome():
    assert chat_service._is_cancel_input({"recipient_selection_outcome": "cancelled"})
    assert chat_service._is_cancel_input({"account_selection_outcome": "cancelled"})
    assert not chat_service._is_cancel_input({"amount_input_outcome": "submitted", "amount": 5})
    assert not chat_service._is_cancel_input({})


def _patch_resume_input(cancel_value: bool):
    """resume_after_input 의존성을 대체하고 publish 호출을 캡처한다."""
    calls = {"published": 0, "resumed": 0}

    async def _owner(session, uid, cid):
        return None

    async def _consume(session, cs, irid):
        return SimpleNamespace(execution_context_id=uuid4())

    async def _resolve(session, ec):
        return "thread_1", ec

    class _Agent:
        async def resume_input(self, **kw):
            calls["resumed"] += 1

    async def _publish(cs, content="x"):
        calls["published"] += 1

    patches = [
        patch.object(chat_service, "verify_chat_session_owner", _owner),
        patch.object(chat_service, "consume_pending_input", _consume),
        patch.object(chat_service, "_resolve_agent_thread_id", _resolve),
        patch.object(chat_service, "get_agent_client", lambda: _Agent()),
        patch.object(chat_service, "publish_cancellation_done", _publish),
    ]
    return patches, calls


@pytest.mark.asyncio
async def test_resume_input_cancel_publishes_terminal_done():
    patches, calls = _patch_resume_input(cancel_value=True)
    for p in patches:
        p.start()
    try:
        await chat_service.resume_after_input(
            AsyncMock(),
            uuid4(),
            uuid4(),
            "input_1",
            {"recipient_selection_outcome": "cancelled"},
        )
    finally:
        for p in patches:
            p.stop()
    assert calls == {"published": 1, "resumed": 1}


@pytest.mark.asyncio
async def test_resume_input_non_cancel_does_not_publish():
    patches, calls = _patch_resume_input(cancel_value=False)
    for p in patches:
        p.start()
    try:
        await chat_service.resume_after_input(
            AsyncMock(),
            uuid4(),
            uuid4(),
            "input_1",
            {"account_selection_outcome": "selected", "account_ids": ["a"]},
        )
    finally:
        for p in patches:
            p.stop()
    assert calls == {"published": 0, "resumed": 1}
