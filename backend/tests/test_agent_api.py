"""POST /api/v1/agent/chat 프록시 엔드포인트 테스트.

agent 서비스 HTTP 호출(call_agent_chat)을 monkeypatch로 대체해
게이트웨이 계층의 봉투 변환만 검증한다.
"""

from fastapi import HTTPException, status

from backend.api import agent_api

_AGENT_REPLY = {
    "reply": "생활비통장 430,000원입니다.",
    "status": "completed",
    "thread_id": "abc123",
    "prompt_for": None,
}


def test_agent_chat_success_envelope(client, monkeypatch):
    async def fake_call(payload: dict) -> dict:
        assert payload["message"] == "생활비 통장 잔액 얼마야?"
        return dict(_AGENT_REPLY)

    monkeypatch.setattr(agent_api, "call_agent_chat", fake_call)

    response = client.post(
        "/api/v1/agent/chat", json={"message": "생활비 통장 잔액 얼마야?"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["reply"] == _AGENT_REPLY["reply"]
    assert body["data"]["status"] == "completed"
    assert body["data"]["thread_id"] == "abc123"


def test_agent_chat_forwards_thread_id(client, monkeypatch):
    captured = {}

    async def fake_call(payload: dict) -> dict:
        captured.update(payload)
        return dict(_AGENT_REPLY)

    monkeypatch.setattr(agent_api, "call_agent_chat", fake_call)

    client.post(
        "/api/v1/agent/chat",
        json={"message": "1번", "thread_id": "thread-1", "user_id": "user_001"},
    )

    assert captured["thread_id"] == "thread-1"
    assert captured["user_id"] == "user_001"


def test_agent_chat_error_envelope_when_agent_down(client, monkeypatch):
    async def fake_call(payload: dict) -> dict:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="에이전트 서비스에 연결할 수 없습니다.",
        )

    monkeypatch.setattr(agent_api, "call_agent_chat", fake_call)

    response = client.post("/api/v1/agent/chat", json={"message": "잔액 알려줘"})

    assert response.status_code == 502
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "HTTP_ERROR"
    assert "연결할 수 없습니다" in body["error"]["message"]


def test_agent_chat_validates_empty_message(client):
    response = client.post("/api/v1/agent/chat", json={"message": ""})

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "REQUEST_VALIDATION_ERROR"
