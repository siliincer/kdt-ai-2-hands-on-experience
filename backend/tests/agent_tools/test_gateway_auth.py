"""Agent Tool API 서비스 인증 + 공통 Context 의존성 검증.

미니 FastAPI 앱에 의존성만 건 라우트를 달아 토큰/스코프 게이트를 확인한다.
get_db 는 DB 없이 통과시키고(resolve_context 는 monkeypatch), 실제 검증 분기는
test_execution_context_service 가 담당한다.
"""

from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

import backend.security.agent_service_auth as auth_mod
import backend.security.execution_context as ctx_mod
from backend.core.exceptions import exception_handlers
from backend.db.postgres import get_db
from backend.schemas.execution_context import ResolvedExecutionContext
from backend.security.agent_service_auth import verify_agent_service_token
from backend.security.execution_context import get_agent_tool_context, require_scope

_TOKEN = "test-service-token"


def _resolved(scopes: list[str]) -> ResolvedExecutionContext:
    return ResolvedExecutionContext(
        execution_context_id=uuid4(),
        user_id=uuid4(),
        chat_session_id=uuid4(),
        agent_thread_id="thread_1",
        scopes=scopes,
        timezone="Asia/Seoul",
    )


@pytest.fixture(autouse=True)
def _known_token(monkeypatch):
    monkeypatch.setattr(auth_mod.settings, "AGENT_SERVICE_TOKEN", SecretStr(_TOKEN))


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    for exc_class, handler in exception_handlers.items():
        app.add_exception_handler(exc_class, handler)

    @app.get("/svc-only", dependencies=[Depends(verify_agent_service_token)])
    def _svc_only():
        return {"ok": True}

    @app.get("/ctx")
    def _ctx(context: ResolvedExecutionContext = Depends(get_agent_tool_context)):
        return {"user_id": str(context.user_id)}

    @app.get("/scoped")
    def _scoped(
        context: ResolvedExecutionContext = Depends(require_scope("transfer:request")),
    ):
        return {"ok": True}

    async def _fake_db():
        yield None

    app.dependency_overrides[get_db] = _fake_db
    return TestClient(app)


def _auth(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Execution-Context-Id": str(uuid4()),
    }


def test_missing_token_rejected(client):
    response = client.get("/svc-only")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_SERVICE_TOKEN"


def test_wrong_token_rejected(client):
    response = client.get("/svc-only", headers=_auth("wrong"))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_SERVICE_TOKEN"


def test_correct_token_passes(client):
    response = client.get("/svc-only", headers=_auth(_TOKEN))
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_context_dependency_returns_user(client, monkeypatch):
    async def _resolve(session, raw):
        return _resolved(["account:read"])

    monkeypatch.setattr(ctx_mod, "resolve_context", _resolve)

    response = client.get("/ctx", headers=_auth(_TOKEN))
    assert response.status_code == 200
    assert "user_id" in response.json()


def test_scope_gate_rejects_missing_scope(client, monkeypatch):
    async def _resolve(session, raw):
        return _resolved(["account:read"])  # transfer:request 없음

    monkeypatch.setattr(ctx_mod, "resolve_context", _resolve)

    response = client.get("/scoped", headers=_auth(_TOKEN))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_SCOPE"


def test_scope_gate_allows_present_scope(client, monkeypatch):
    async def _resolve(session, raw):
        return _resolved(["account:read", "transfer:request"])

    monkeypatch.setattr(ctx_mod, "resolve_context", _resolve)

    response = client.get("/scoped", headers=_auth(_TOKEN))
    assert response.status_code == 200
