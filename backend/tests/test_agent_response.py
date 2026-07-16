"""Agent Tool API 오류 envelope(D2)과 AgentToolError 핸들러 검증.

성공 envelope 은 공통 `{success, message, data}` 이고, 오류 envelope 만
`error.{category, code, message, retryable}` 로 다르다는 점을 확인한다.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.agent_exceptions import AgentToolError
from backend.core.exceptions import exception_handlers
from backend.utils.agent_response import agent_error_response, agent_success_response


@pytest.fixture
def app():
    app = FastAPI()
    for exc_class, handler in exception_handlers.items():
        app.add_exception_handler(exc_class, handler)

    @app.get("/raise-invalid-context")
    def _invalid_context():
        raise AgentToolError.invalid_execution_context()

    @app.get("/raise-expired")
    def _expired():
        raise AgentToolError.execution_context_expired()

    @app.get("/raise-scope")
    def _scope():
        raise AgentToolError.insufficient_scope()

    @app.get("/raise-temporary")
    def _temporary():
        raise AgentToolError.backend_temporary_error()

    @app.get("/raise-with-details")
    def _with_details():
        raise AgentToolError(
            status_code=409,
            category="request_error",
            code="IDEMPOTENCY_KEY_CONFLICT",
            message="같은 멱등성 키에 다른 요청을 사용할 수 없습니다.",
            retryable=False,
            details={"idempotency_key": "k-1"},
        )

    @app.get("/raise-in-progress")
    def _in_progress():
        raise AgentToolError.idempotency_request_in_progress()

    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_invalid_context_envelope(client):
    response = client.get("/raise-invalid-context")
    assert response.status_code == 401
    body = response.json()
    assert body["success"] is False
    error = body["error"]
    assert error["category"] == "authentication_error"
    assert error["code"] == "INVALID_EXECUTION_CONTEXT"
    assert error["retryable"] is False
    assert "message" in error
    # 오류 envelope 에는 최상위 data 키가 없다.
    assert "data" not in body


def test_expired_maps_to_410(client):
    response = client.get("/raise-expired")
    assert response.status_code == 410
    error = response.json()["error"]
    assert error["code"] == "EXECUTION_CONTEXT_EXPIRED"
    assert error["category"] == "state_error"


def test_insufficient_scope_maps_to_403(client):
    response = client.get("/raise-scope")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_SCOPE"


def test_temporary_error_is_retryable(client):
    response = client.get("/raise-temporary")
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "BACKEND_TEMPORARY_ERROR"
    assert error["retryable"] is True


def test_details_are_passed_through(client):
    response = client.get("/raise-with-details")
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["details"] == {"idempotency_key": "k-1"}


def test_in_progress_emits_retry_after_header(client):
    """처리 중 409 는 Retry-After 헤더를 함께 반환한다(계약 24.4)."""
    response = client.get("/raise-in-progress")
    assert response.status_code == 409
    assert response.headers["retry-after"] == "1"
    error = response.json()["error"]
    assert error["code"] == "IDEMPOTENCY_REQUEST_IN_PROGRESS"
    assert error["retryable"] is True


def test_error_builder_omits_details_when_none():
    resp = agent_error_response(
        status_code=401,
        category="authentication_error",
        code="INVALID_SERVICE_TOKEN",
        message="fail",
    )
    import json

    payload = json.loads(bytes(resp.body))
    assert payload["error"] == {
        "category": "authentication_error",
        "code": "INVALID_SERVICE_TOKEN",
        "message": "fail",
        "retryable": False,
    }


def test_success_builder_uses_common_envelope():
    resp = agent_success_response(message="ok", data={"accounts": []})
    assert resp.success is True
    assert resp.message == "ok"
    assert resp.data == {"accounts": []}
