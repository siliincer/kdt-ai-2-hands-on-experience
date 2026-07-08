from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.schemas.sse import SseTicketResponse
from backend.services.sse_ticket_service import consume_sse_ticket, grant_sse_ticket


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.set = AsyncMock()
    redis.hset = AsyncMock()
    redis.expire = AsyncMock()
    redis.getdel = AsyncMock(return_value=None)
    return redis


@pytest.mark.asyncio
async def test_grant_sse_ticket_stores_ticket_and_user_cache(mock_redis):
    user_id = uuid4()

    ticket = await grant_sse_ticket(mock_redis, user_id)

    assert isinstance(ticket, SseTicketResponse)
    assert ticket.sse_session_id is not None
    assert ticket.expires_in > 0
    mock_redis.set.assert_awaited_once()
    mock_redis.hset.assert_awaited_once()
    mock_redis.expire.assert_awaited_once()


@pytest.mark.asyncio
async def test_consume_sse_ticket_returns_user_id_and_deletes_key(mock_redis):
    user_id = uuid4()
    sse_session_id = uuid4()
    mock_redis.getdel = AsyncMock(return_value=str(user_id))

    result = await consume_sse_ticket(mock_redis, sse_session_id)

    assert result == user_id
    mock_redis.getdel.assert_awaited_once()


@pytest.mark.asyncio
async def test_consume_sse_ticket_returns_none_for_invalid_ticket(mock_redis):
    result = await consume_sse_ticket(mock_redis, uuid4())
    assert result is None


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


def test_connect_sse_streams_mock_events(client: TestClient):
    from backend.db.redis import get_redis_cache
    from backend.main import app

    user_id = uuid4()
    sse_session_id = uuid4()

    redis = AsyncMock()
    redis.getdel = AsyncMock(return_value=str(user_id))

    async def override_redis():
        yield redis

    app.dependency_overrides[get_redis_cache] = override_redis

    try:
        with client.stream(
            "GET",
            f"/api/v1/sse/connect?sse_session_id={sse_session_id}",
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")
            body = "".join(response.iter_text())
            assert "SSE 연결이 설정되었습니다." in body
            assert "[DONE]" in body
    finally:
        app.dependency_overrides.clear()
