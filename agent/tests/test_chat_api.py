"""Agent HTTP 진입점 회귀 테스트."""


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_legacy_chat_api_is_not_exposed(client):
    """Agent 직접 /chat 호출이 구형 Workflow로 우회하지 못한다."""
    response = client.post("/chat", json={"message": "잔액 알려줘"})
    assert response.status_code == 404


def test_openapi_exposes_only_current_execution_entrypoint(client):
    """업무 실행은 계약 기반 내부 Execution API로만 시작한다."""
    paths = client.get("/openapi.json").json()["paths"]
    assert "/chat" not in paths
    assert "/internal/v1/executions" in paths
