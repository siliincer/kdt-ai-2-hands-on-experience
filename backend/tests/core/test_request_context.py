"""X-Request-Id 바인딩 검증(로그 상관관계용, 계약 6장).

중복 방지(Idempotency-Key)와 목적이 다르므로 두 값을 매핑하지 않는다 — 여기서는
"헤더를 받으면 그대로 쓰고, 없으면 생성하고, 감사 로그가 그 값을 집어간다"만 검증한다.
"""

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import Request

from backend.core.request_context import (
    MAX_REQUEST_ID_LENGTH,
    bind_request_id,
    get_request_id,
    set_request_id,
)
from backend.schemas.execution_context import ResolvedExecutionContext
from backend.services import financial_audit_service


def _fake_request(path: str = "/api/v1/agent-tools/accounts") -> Request:
    """의존성은 method/url.path 만 읽으므로 가짜 객체로 충분하다(타입만 맞춰 준다)."""
    return cast(Request, SimpleNamespace(method="POST", url=SimpleNamespace(path=path)))


def test_set_request_id_keeps_agent_value():
    """Agent 가 보낸 값을 그대로 유지해야 로그 대조가 된다."""
    assert set_request_id("req_execute_123") == "req_execute_123"
    assert get_request_id() == "req_execute_123"


def test_set_request_id_generates_when_missing():
    """헤더가 없으면 Backend 가 생성해 서버 로그만으로도 추적 가능하게 한다."""
    generated = set_request_id(None)
    assert generated.startswith("req_")
    assert get_request_id() == generated


def test_set_request_id_trims_and_caps_length():
    """외부 입력이므로 공백 제거 + 길이 상한(로그 오염 방지)."""
    assert set_request_id("  req_padded  ") == "req_padded"
    capped = set_request_id("x" * (MAX_REQUEST_ID_LENGTH + 50))
    assert len(capped) == MAX_REQUEST_ID_LENGTH
    # 공백만 있으면 생성값으로 대체
    assert set_request_id("   ").startswith("req_")


@pytest.mark.asyncio
async def test_bind_request_id_dependency_binds_header():
    resolved = await bind_request_id(_fake_request(), x_request_id="req_webhook_9")
    assert resolved == "req_webhook_9"
    assert get_request_id() == "req_webhook_9"


@pytest.mark.asyncio
async def test_audit_record_picks_up_bound_request_id():
    """감사 로그의 request_id 가 현재 요청의 X-Request-Id 로 채워진다."""
    set_request_id("req_audit_42")
    captured = {}

    async def _create(session, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(**kwargs)

    context = ResolvedExecutionContext(
        execution_context_id=uuid4(),
        user_id=uuid4(),
        chat_session_id=uuid4(),
        agent_thread_id="thread_1",
        scopes=["transfer:request"],
        timezone="Asia/Seoul",
    )

    with patch.object(financial_audit_service, "create_financial_audit_log", _create):
        await financial_audit_service.record(
            AsyncMock(),
            context,
            event_type="TRANSFER_EXECUTED",
            operation="external_transfer",
            outcome="completed",
        )

    assert captured["request_id"] == "req_audit_42"


@pytest.mark.asyncio
async def test_audit_record_explicit_request_id_wins():
    set_request_id("req_bound")
    captured = {}

    async def _create(session, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(**kwargs)

    context = ResolvedExecutionContext(
        execution_context_id=uuid4(),
        user_id=uuid4(),
        chat_session_id=uuid4(),
        agent_thread_id="thread_1",
        scopes=[],
        timezone="Asia/Seoul",
    )

    with patch.object(financial_audit_service, "create_financial_audit_log", _create):
        await financial_audit_service.record(
            AsyncMock(),
            context,
            event_type="E",
            operation="o",
            outcome="completed",
            request_id="req_explicit",
        )

    assert captured["request_id"] == "req_explicit"
