"""Agent Tool API 라우터 취합.

공통 Prefix `/agent-tools` 를 붙여 각 도메인 라우터를 모은다. main.py 는 이 라우터를
`/api/v1` prefix 로 mount 하므로 최종 경로는 `/api/v1/agent-tools/*` 가 된다(계약 3장).
"""

from fastapi import APIRouter

from .account_api import account_router
from .transaction_api import transaction_router

agent_tools_router = APIRouter(prefix="/agent-tools")
agent_tools_router.include_router(account_router)
agent_tools_router.include_router(transaction_router)

__all__ = ["agent_tools_router"]
