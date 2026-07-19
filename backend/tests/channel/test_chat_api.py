from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.models.confirmation import ConfirmationStatus
from backend.services import chat_service, chat_session_service
from backend.services.mock_agent_driver import (
    _extract_autotransfer_args,
    _extract_transfer_args,
    _is_alias_intent,
    _is_autotransfer_intent,
    _is_transfer_intent,
)

# --- 목 드라이버 순수 함수 ---------------------------------------------------


def test_is_transfer_intent_detects_keywords():
    assert _is_transfer_intent("김철수에게 송금하고 싶어")
    assert _is_transfer_intent("3만원 보내줘")
    assert not _is_transfer_intent("이번 달 잔액 알려줘")


def test_extract_transfer_args_parses_amount_and_account():
    args = _extract_transfer_args("110-123-999888 로 50,000원 송금")
    assert args["amount"] == "50000"
    assert args["account"] == "110-123-999888"
    # 파싱 안 된 필드는 샘플로 채워진다
    assert args["name"]
    assert args["bank"]


def test_is_autotransfer_intent_wins_over_transfer():
    # "자동이체" 는 "이체"(송금 키워드)를 포함하지만 자동이체로 먼저 잡혀야 한다
    assert _is_autotransfer_intent("자동이체 등록해줘")
    assert _is_autotransfer_intent("정기결제 걸어줘")
    assert not _is_autotransfer_intent("김철수에게 송금")


def test_extract_autotransfer_args_parses_amount_and_day():
    args = _extract_autotransfer_args("매월 25일 200,000원 자동이체")
    assert args["amount"] == "200000"
    assert args["day"] == "매월 25일"
    assert args["account"]  # 파싱 안 되면 샘플


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
        result = await chat_session_service.resolve_chat_session(
            session, user_id, chat_session_id
        )
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
    with patch.object(
        chat_session_service, "get_chat_session", AsyncMock(return_value=None)
    ):
        with pytest.raises(HTTPException) as exc:
            await chat_session_service.verify_chat_session_owner(
                session, uuid4(), uuid4()
            )
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


# --- 설정 confirm_modal → Confirmation 생명주기(_apply_setting_confirmation) ---------


def test_is_alias_intent_detects_keywords():
    assert _is_alias_intent("계좌 별칭 바꿔줘")
    assert _is_alias_intent("계좌 이름 변경")
    assert not _is_alias_intent("송금하고 싶어")


def _confirmation(user_id, status=ConfirmationStatus.PENDING, expires_in=300):
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        status=status,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
    )


@pytest.mark.asyncio
async def test_apply_setting_approve_marks_approved():
    user_id = uuid4()
    conf = _confirmation(user_id)
    calls = {"approve": 0, "invalidate": 0}

    async def _get(session, cid):
        return conf

    async def _approve(session, c):
        calls["approve"] += 1

    async def _invalidate(session, c):
        calls["invalidate"] += 1

    with (
        patch.object(chat_service, "get_confirmation_by_id", _get),
        patch.object(chat_service.confirmation_service, "approve", _approve),
        patch.object(chat_service.confirmation_service, "invalidate", _invalidate),
    ):
        await chat_service._apply_setting_confirmation(
            AsyncMock(), user_id, str(conf.id), "approve"
        )
    assert calls == {"approve": 1, "invalidate": 0}


@pytest.mark.asyncio
async def test_apply_setting_cancel_invalidates():
    user_id = uuid4()
    conf = _confirmation(user_id)
    calls = {"approve": 0, "invalidate": 0}

    async def _get(session, cid):
        return conf

    async def _approve(session, c):
        calls["approve"] += 1

    async def _invalidate(session, c):
        calls["invalidate"] += 1

    with (
        patch.object(chat_service, "get_confirmation_by_id", _get),
        patch.object(chat_service.confirmation_service, "approve", _approve),
        patch.object(chat_service.confirmation_service, "invalidate", _invalidate),
    ):
        await chat_service._apply_setting_confirmation(
            AsyncMock(), user_id, str(conf.id), "cancelled"
        )
    assert calls == {"approve": 0, "invalidate": 1}


@pytest.mark.asyncio
async def test_apply_setting_other_user_is_404():
    conf = _confirmation(uuid4())  # 다른 사용자

    async def _get(session, cid):
        return conf

    with patch.object(chat_service, "get_confirmation_by_id", _get):
        with pytest.raises(HTTPException) as exc:
            await chat_service._apply_setting_confirmation(
                AsyncMock(), uuid4(), str(conf.id), "approve"
            )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_apply_setting_expired_is_410():
    user_id = uuid4()
    conf = _confirmation(user_id, expires_in=-1)

    async def _get(session, cid):
        return conf

    with patch.object(chat_service, "get_confirmation_by_id", _get):
        with pytest.raises(HTTPException) as exc:
            await chat_service._apply_setting_confirmation(
                AsyncMock(), user_id, str(conf.id), "approve"
            )
    assert exc.value.status_code == 410


@pytest.mark.asyncio
async def test_apply_setting_non_pending_is_409():
    user_id = uuid4()
    conf = _confirmation(user_id, status=ConfirmationStatus.APPROVED)

    async def _get(session, cid):
        return conf

    with patch.object(chat_service, "get_confirmation_by_id", _get):
        with pytest.raises(HTTPException) as exc:
            await chat_service._apply_setting_confirmation(
                AsyncMock(), user_id, str(conf.id), "approve"
            )
    assert exc.value.status_code == 409


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
