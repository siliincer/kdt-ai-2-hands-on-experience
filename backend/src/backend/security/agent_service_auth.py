"""Agent → Backend Tool API 서비스 인증.

계약 4.1·6.2: /api/v1/agent-tools/* 는 `Authorization: Bearer <AGENT_SERVICE_TOKEN>` 로
서비스 간 인증한다. Frontend 사용자 토큰(JWT)과는 다른 Secret 이며 반드시 분리한다.
실패는 Agent Tool 오류 envelope(401)으로 반환한다.
"""

from __future__ import annotations

import secrets

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..core.agent_exceptions import AgentToolError
from ..core.load_environment_var import settings

# auto_error=False: 헤더 누락 시 FastAPI 기본 403 대신 우리 envelope 로 통일한다.
_service_bearer = HTTPBearer(auto_error=False)


def verify_agent_service_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_service_bearer),
) -> None:
    """서비스 토큰을 상수시간 비교로 검증한다. 실패 시 INVALID_SERVICE_TOKEN(401)."""
    expected = settings.AGENT_SERVICE_TOKEN.get_secret_value()
    if credentials is None or not secrets.compare_digest(
        credentials.credentials, expected
    ):
        raise AgentToolError.invalid_service_token()
