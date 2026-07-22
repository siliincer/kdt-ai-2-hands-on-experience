"""요청 추적 id(X-Request-Id) 바인딩 — 로그 상관관계용(계약 6장).

목적은 **로그 추적**이다. Agent 와 Backend 가 같은 `X-Request-Id` 를 남기면 한 값으로
"수신했는지 / 어떤 Tool·Webhook 을 처리했는지 / 어디서 실패했는지"를 이어서 볼 수 있다.

**중복 실행 방지와는 무관하다.** 같은 상태 변경 요청이 재전달돼도 한 번만 처리되게 하는
것은 `Idempotency-Key`(`services/idempotency_service.py`)의 책임이며 두 값은 별개다.

요청 스코프 저장은 ContextVar 를 쓴다. FastAPI 는 요청마다 별도 task 에서 실행하므로
요청 간 값이 섞이지 않고, 의존성에서 심어 두면 같은 요청의 서비스 계층(감사 로그 등)에서
꺼내 쓸 수 있다.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from uuid import uuid4

from fastapi import Header, Request

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-Id"

# 외부 입력이므로 로그 오염을 막기 위해 길이를 제한한다.
MAX_REQUEST_ID_LENGTH = 128

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
# ContextVar은 비동기/스레드 환경에서 각 태스크마다 독립된 값의 흐름을 가짐.


def set_request_id(value: str | None) -> str:
    """요청 추적 id 를 현재 요청 스코프에 바인딩한다.

    Agent 가 헤더를 안 보냈으면 Backend 가 생성해 서버 로그만으로도 추적 가능하게 한다.
    """
    trimmed = (value or "").strip()[:MAX_REQUEST_ID_LENGTH]
    resolved = trimmed or f"req_{uuid4().hex[:12]}"
    _request_id.set(resolved)
    return resolved


def get_request_id() -> str | None:
    """현재 요청의 추적 id. 바인딩되지 않았으면 None."""
    return _request_id.get()


async def bind_request_id(
    request: Request,
    x_request_id: str | None = Header(default=None, alias=REQUEST_ID_HEADER),
) -> str:
    """FastAPI 의존성: `X-Request-Id` 를 바인딩하고 수신 로그를 남긴다.

    Agent 가 호출하는 표면(Webhook·agent-tools)에 걸어 두면, Agent 로그의 같은 값으로
    Backend 수신 여부와 처리 경로를 대조할 수 있다.
    """
    resolved = set_request_id(x_request_id)
    logger.info(
        "request received request_id=%s method=%s path=%s",
        resolved,
        request.method,
        request.url.path,
    )
    return resolved
