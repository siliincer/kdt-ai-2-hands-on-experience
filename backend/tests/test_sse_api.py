from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.schemas.sse import (
    AgentStreamEvent,
    AgentStreamEventType,
    SseTicketContext,
    SseTicketResponse,
)
from backend.services.agent_stream_producer import (
    agent_stream_key,
    fields_to_event,
    publish_agent_event,
)
from backend.services.sse_service import relay_agent_stream
from backend.services.sse_ticket_service import consume_sse_ticket, grant_sse_ticket


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.set = AsyncMock()
    redis.hset = AsyncMock()
    redis.expire = AsyncMock()
    redis.getdel = AsyncMock(return_value=None)
    return redis


# --- 티켓 서비스 (chat_session_id 바인딩) ---------------------------------


@pytest.mark.asyncio
async def test_grant_sse_ticket_binds_chat_session(mock_redis):
    user_id = uuid4()
    chat_session_id = uuid4()

    ticket = await grant_sse_ticket(mock_redis, user_id, chat_session_id)

    assert isinstance(ticket, SseTicketResponse)
    assert ticket.sse_session_id is not None
    assert ticket.chat_session_id == chat_session_id
    assert ticket.expires_in > 0
    mock_redis.set.assert_awaited_once()
    mock_redis.hset.assert_awaited_once()
    mock_redis.expire.assert_awaited_once()


@pytest.mark.asyncio
async def test_consume_sse_ticket_returns_context_and_deletes_key(mock_redis):
    import json

    user_id = uuid4()
    chat_session_id = uuid4()
    sse_session_id = uuid4()
    mock_redis.getdel = AsyncMock(
        return_value=json.dumps(
            {"user_id": str(user_id), "chat_session_id": str(chat_session_id)}
        )
    )

    context = await consume_sse_ticket(mock_redis, sse_session_id)

    assert isinstance(context, SseTicketContext)
    assert context.user_id == user_id
    assert context.chat_session_id == chat_session_id
    mock_redis.getdel.assert_awaited_once()


@pytest.mark.asyncio
async def test_consume_sse_ticket_returns_none_for_invalid_ticket(mock_redis):
    result = await consume_sse_ticket(mock_redis, uuid4())
    assert result is None


# --- 프로듀서 (XADD) -----------------------------------------------------


@pytest.mark.asyncio
async def test_publish_agent_event_xadds_and_sets_ttl():
    chat_session_id = uuid4()
    redis_stream = AsyncMock()
    redis_stream.xadd = AsyncMock(return_value="1-0")
    redis_stream.expire = AsyncMock()

    event = AgentStreamEvent(
        event_type=AgentStreamEventType.TOOL_CALL,
        content="get_balance",
        metadata={"tool": "get_balance"},
    )
    message_id = await publish_agent_event(redis_stream, chat_session_id, event)

    assert message_id == "1-0"
    redis_stream.xadd.assert_awaited_once()
    args, kwargs = redis_stream.xadd.call_args
    assert args[0] == agent_stream_key(chat_session_id)
    # fields 는 positional/keyword 어느 쪽으로 전달돼도 통과하도록 조회
    fields = kwargs.get("fields", args[1] if len(args) > 1 else None)
    assert fields["event_type"] == "tool_call"
    assert kwargs.get("maxlen") is not None
    redis_stream.expire.assert_awaited_once()


def test_fields_to_event_roundtrip():
    from backend.services.agent_stream_producer import _to_fields

    event = AgentStreamEvent(
        event_type=AgentStreamEventType.NEED_APPROVAL,
        content="송금 승인?",
        approval_id="appv_1",
        metadata={"amount": 1000},
    )
    restored = fields_to_event(_to_fields(event))
    assert restored == event


# --- 릴레이 (XREAD BLOCK) ------------------------------------------------


class FakeStreamRedis:
    """xread 응답을 스크립트대로 반환하는 최소 페이크."""

    def __init__(self, batches):
        self._batches = list(batches)

    async def xread(self, streams, block=None, count=None):
        if self._batches:
            return self._batches.pop(0)
        return None


@pytest.mark.asyncio
async def test_relay_survives_xread_timeout_and_continues():
    """idle 블로킹 XREAD 가 redis TimeoutError 를 던져도 크래시하지 않고
    keep-alive(ping) 후 계속 읽어 done 까지 도달해야 한다(승인 대기 스트림 회귀)."""
    import redis.exceptions

    chat_session_id = uuid4()
    key = agent_stream_key(chat_session_id)

    class FlakyRedis:
        def __init__(self):
            self._calls = 0

        async def xread(self, streams, block=None, count=None):
            self._calls += 1
            if self._calls == 1:
                raise redis.exceptions.TimeoutError("idle block timeout")
            return [[key, [("9-0", {"event_type": "done", "content": "끝"})]]]

    events = [ev async for ev in relay_agent_stream(FlakyRedis(), chat_session_id)]

    assert any(ev.comment == "ping" for ev in events)  # 타임아웃 → ping 으로 흡수
    assert any(ev.raw_data == "[DONE]" for ev in events)  # 이후 done 도달


@pytest.mark.asyncio
async def test_relay_streams_events_until_done():
    chat_session_id = uuid4()
    key = agent_stream_key(chat_session_id)
    fake = FakeStreamRedis(
        [
            [[key, [("1-0", {"event_type": "status", "content": "계획 수립"})]]],
            [[key, [("2-0", {"event_type": "done", "content": "완료"})]]],
        ]
    )

    events = [ev async for ev in relay_agent_stream(fake, chat_session_id)]

    # status 이벤트: data 로 AgentStreamEvent 전달, event 필드 = "status"
    status_events = [ev for ev in events if ev.event == "status"]
    assert len(status_events) == 1
    assert status_events[0].data.content == "계획 수립"
    assert status_events[0].id == "1-0"

    # done sentinel: raw_data "[DONE]"
    assert any(ev.raw_data == "[DONE]" for ev in events)


@pytest.mark.asyncio
async def test_relay_resumes_from_last_event_id():
    chat_session_id = uuid4()
    key = agent_stream_key(chat_session_id)
    captured = {}

    class CapturingRedis(FakeStreamRedis):
        async def xread(self, streams, block=None, count=None):
            captured["start_id"] = streams[key]
            return [[key, [("5-0", {"event_type": "done", "content": "x"})]]]

    fake = CapturingRedis([])
    _ = [ev async for ev in relay_agent_stream(fake, chat_session_id, "4-0")]

    assert captured["start_id"] == "4-0"


# --- E2E (connect 엔드포인트) --------------------------------------------


def test_connect_sse_rejects_invalid_ticket(client: TestClient):
    from backend.db.redis import get_redis_cache
    from backend.main import app

    redis = AsyncMock()
    redis.getdel = AsyncMock(return_value=None)

    async def override_redis():
        yield redis

    app.dependency_overrides[get_redis_cache] = override_redis
    try:
        response = client.get(f"/api/v1/sse/connect?sse_session_id={uuid4()}")
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_connect_sse_relays_stream_events(client: TestClient):
    import json

    from backend.db.redis import get_redis_cache, get_redis_stream
    from backend.main import app

    user_id = uuid4()
    chat_session_id = uuid4()
    sse_session_id = uuid4()
    key = agent_stream_key(chat_session_id)

    cache = AsyncMock()
    cache.getdel = AsyncMock(
        return_value=json.dumps(
            {"user_id": str(user_id), "chat_session_id": str(chat_session_id)}
        )
    )

    stream = FakeStreamRedis(
        [[[key, [("1-0", {"event_type": "done", "content": "완료됨"})]]]]
    )

    async def override_cache():
        yield cache

    async def override_stream():
        yield stream

    app.dependency_overrides[get_redis_cache] = override_cache
    app.dependency_overrides[get_redis_stream] = override_stream

    try:
        with client.stream(
            "GET",
            f"/api/v1/sse/connect?sse_session_id={sse_session_id}",
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")
            body = "".join(response.iter_text())
            assert "완료됨" in body
            assert "[DONE]" in body
    finally:
        app.dependency_overrides.clear()
