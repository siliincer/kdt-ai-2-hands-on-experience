"""보안 응답 헤더(secure 라이브러리) — 순수 ASGI 미들웨어.

왜 순수 ASGI 인가:
  이 백엔드는 SSE 장수명 스트리밍(`/api/v1/sse/connect`)을 제공한다. Starlette
  `BaseHTTPMiddleware`(= `@app.middleware("http")`)는 응답 본문을 감싸 스트리밍을
  버퍼링·간섭할 수 있으므로, 여기서는 `http.response.start` 의 헤더만 주입하고 본문은
  절대 건드리지 않는 ASGI 미들웨어를 쓴다.

헤더 구성(JSON API 기준, secure 2.x):
  - Content-Security-Policy: default-src 'none' — JSON 응답은 아무 리소스도 로드/실행하지
    않는다. 단 Swagger/ReDoc 문서는 CDN 을 로드하므로 이 CSP 가 페이지를 깨뜨린다 →
    문서 경로에서는 CSP 만 제외한다(나머지 헤더는 유지).
  - Strict-Transport-Security: HTTPS 에서만 의미(개발 http 에서는 브라우저가 무시).
  - X-Frame-Options: DENY / X-Content-Type-Options: nosniff / Referrer-Policy: no-referrer
  - Permissions-Policy: 위치·마이크·카메라 비활성 / COOP·CORP: same-origin

서버 배너(`Server: uvicorn`)는 여기서 숨기지 않는다. uvicorn 이 ASGI 미들웨어 하류에서
Server 헤더를 붙이므로 빈 Server 를 주입하면 헤더가 중복될 뿐이다. 숨기려면 uvicorn 을
`server_header=False`(`--no-server-header`)로 띄우거나 nginx 에서 제거한다.
"""

import secure
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Swagger UI / ReDoc / OpenAPI 스키마 — CDN 자산을 로드하므로 엄격한 CSP 를 적용하지 않는다.
_DOCS_PATHS = frozenset(
    {
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
        "/openapi.json",
    }
)

_CSP_HEADER = "content-security-policy"


def _build_secure() -> secure.Secure:
    """JSON API 에 맞춘 보안 헤더 집합을 만든다."""
    return secure.Secure(
        hsts=secure.StrictTransportSecurity().max_age(31_536_000).include_subdomains(),
        # JSON API: 아무것도 로드/실행/프레임하지 않는다.
        csp=(
            secure.ContentSecurityPolicy()
            .default_src("'none'")
            .base_uri("'none'")
            .form_action("'none'")
            .frame_ancestors("'none'")
        ),
        xfo=secure.XFrameOptions().deny(),
        xcto=secure.XContentTypeOptions(),  # nosniff
        referrer=secure.ReferrerPolicy().no_referrer(),
        permissions=secure.PermissionsPolicy().geolocation().microphone().camera(),
        # TODO(BE): permission은 차후 기능 확장(음성 지원 등)에 따라 해제 가능
        coop=secure.CrossOriginOpenerPolicy(),  # same-origin
        corp=secure.CrossOriginResourcePolicy(),  # same-origin
    )


class SecureHeadersMiddleware:
    """모든 HTTP 응답에 보안 헤더를 주입하는 ASGI 미들웨어(본문 무간섭)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        header_items = list(_build_secure().headers.items())
        # 문서 경로용: CSP 만 제외한 집합(나머지 보안 헤더는 그대로 적용).
        self._all: list[tuple[str, str]] = header_items
        self._without_csp: list[tuple[str, str]] = [
            (name, value) for name, value in header_items if name.lower() != _CSP_HEADER
        ]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers_to_set = self._without_csp if scope["path"] in _DOCS_PATHS else self._all

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(raw=message["headers"])
                for name, value in headers_to_set:
                    headers[name] = value
            await send(message)

        await self.app(scope, receive, send_with_headers)
