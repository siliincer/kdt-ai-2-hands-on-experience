"""에이전트 서비스 HTTP 클라이언트.

backend 게이트웨이가 agent 서비스(/chat)를 호출하는 유일한 창구.
에이전트 장애/지연은 HTTPException으로 변환해 기존 예외 핸들러가
표준 에러 응답({success: false, error: {...}})으로 감싸게 한다.
"""

from __future__ import annotations

import httpx
from fastapi import HTTPException, status

from ..core.load_environment_var import settings

# LLM 다회 호출 워크플로우 대비 넉넉한 읽기 타임아웃
_TIMEOUT = httpx.Timeout(60.0, connect=5.0)


async def call_agent_chat(payload: dict) -> dict:
    """agent 서비스의 POST /chat을 호출해 응답 dict를 반환한다."""
    url = f"{settings.AGENT_SERVICE_URL.rstrip('/')}/chat"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(url, json=payload)
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="에이전트 응답이 지연되고 있습니다. 잠시 후 다시 시도해 주세요.",
        )
    except httpx.HTTPError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="에이전트 서비스에 연결할 수 없습니다.",
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="에이전트 서비스 처리 중 오류가 발생했습니다.",
        )

    return response.json()
