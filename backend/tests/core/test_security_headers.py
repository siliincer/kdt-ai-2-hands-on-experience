"""보안 응답 헤더(SecureHeadersMiddleware) 검증."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.security_headers import SecureHeadersMiddleware

_EXPECTED = {
    "content-security-policy",
    "strict-transport-security",
    "x-frame-options",
    "x-content-type-options",
    "referrer-policy",
    "permissions-policy",
    "cross-origin-opener-policy",
    "cross-origin-resource-policy",
}


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(SecureHeadersMiddleware)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    @app.get("/docs")
    def fake_docs():
        # 문서 경로에서 CSP 가 제외되는지만 확인(실제 Swagger UI 대체).
        return {"docs": True}

    return app


def test_security_headers_present_on_api_response():
    client = TestClient(_app())
    res = client.get("/ping")

    assert res.status_code == 200
    lower = {k.lower() for k in res.headers}
    assert _EXPECTED <= lower
    assert res.headers["x-frame-options"] == "DENY"
    assert res.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'none'" in res.headers["content-security-policy"]


def test_docs_path_omits_csp_but_keeps_other_headers():
    client = TestClient(_app())
    res = client.get("/docs")

    assert res.status_code == 200
    # CSP 는 문서 경로에서 제외(Swagger CDN 자산 로드 허용)
    assert "content-security-policy" not in {k.lower() for k in res.headers}
    # 나머지 보안 헤더는 그대로 유지
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "DENY"


def test_body_is_untouched():
    client = TestClient(_app())
    res = client.get("/ping")
    assert res.json() == {"ok": True}
