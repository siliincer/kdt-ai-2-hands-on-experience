"""실 Agent 내부 실행 API HTTP 클라이언트 — Backend → Agent 경계.

chat_service 는 mock_agent_driver 대신 이 클라이언트로 Agent Workflow 실행/재개를
요청한다. Agent 는 빠른 202(accepted)만 돌려주고 실제 결과는 Webhook 으로 발행한다
(계약: agent-integration-interface §2, agent/internal_execution_api.py).

- 실행 시작: POST /internal/v1/executions
    {request_id, chat_session_id, execution_context_id, message}
    → 202 {accepted: true, agent_thread_id}
- 재개: POST /internal/v1/executions/{agent_thread_id}/resume
    {request_id, chat_session_id, execution_context_id, resume: {type, ...}}
    → 202 {accepted: true, agent_thread_id}

인증: Authorization: Bearer <BACKEND_SERVICE_TOKEN>(Agent 가 검증). 상관관계용
X-Request-Id 를 요청마다 함께 보낸다(Agent 가 로그에 기록).

값 매핑은 이 경계에서 캡슐화한다. Backend 내부 표현(FE decision, auth_status)을
Agent 계약(approval_outcome, authentication resume)으로 여기서만 번역한다.
"""

from __future__ import annotations

from typing import Any

import httpx

from ..core.load_environment_var import settings

_EXECUTIONS_PATH = "/internal/v1/executions"

# FE 승인 decision → Agent approval_outcome(agent/runtime/hitl.py ApprovalResume).
# "approve" 만 이름이 다르고 나머지는 동일하다.
_APPROVAL_OUTCOME_BY_DECISION = {
    "approve": "approved",
    "change_requested": "change_requested",
    "cancelled": "cancelled",
}


class AgentServiceError(Exception):
    """Agent 실행/재개 요청 실패(커넥션·타임아웃·4xx/5xx).

    로컬 IP/도메인 등 내부 주소가 로그로 새지 않도록 메시지는 타입명·상태코드만
    남긴다(CLAUDE.md 로깅 규칙). 상위에서 사용자에게는 일반 오류로 흡수한다.
    """


class AgentServiceClient:
    """Agent 내부 실행 API 호출 구현.

    httpx.AsyncClient 는 재사용 가능한 커넥션 풀을 갖는다. 팩토리가 인스턴스를
    캐시하므로 프로세스당 풀 1개를 재사용한다.
    """

    def __init__(
        self,
        base_url: str,
        service_token: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(10.0, connect=3.0),
            headers={"Authorization": f"Bearer {service_token}"},
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post(self, url: str, *, json: dict[str, Any], request_id: str) -> dict[str, Any]:
        try:
            response = await self._client.post(url, json=json, headers={"X-Request-Id": request_id})
        except httpx.HTTPError as exc:
            raise AgentServiceError(f"Agent 서비스 연결 실패: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            raise AgentServiceError(f"Agent 실행 요청 실패: HTTP {response.status_code}")
        return response.json()

    async def start_execution(
        self,
        *,
        request_id: str,
        chat_session_id: str,
        execution_context_id: str,
        message: str,
    ) -> str:
        """새 Workflow 실행을 접수시키고 Agent 가 발급한 agent_thread_id 를 돌려준다."""
        data = await self._post(
            _EXECUTIONS_PATH,
            json={
                "request_id": request_id,
                "chat_session_id": chat_session_id,
                "execution_context_id": execution_context_id,
                "message": message,
            },
            request_id=request_id,
        )
        return str(data["agent_thread_id"])

    async def _resume(
        self,
        *,
        agent_thread_id: str,
        request_id: str,
        chat_session_id: str,
        execution_context_id: str,
        resume: dict[str, Any],
    ) -> None:
        await self._post(
            f"{_EXECUTIONS_PATH}/{agent_thread_id}/resume",
            json={
                "request_id": request_id,
                "chat_session_id": chat_session_id,
                "execution_context_id": execution_context_id,
                "resume": resume,
            },
            request_id=request_id,
        )

    async def resume_input(
        self,
        *,
        agent_thread_id: str,
        request_id: str,
        chat_session_id: str,
        execution_context_id: str,
        input_request_id: str,
        value: dict[str, Any],
    ) -> None:
        """일반 입력·선택 회신으로 재개(resume.type=input)."""
        await self._resume(
            agent_thread_id=agent_thread_id,
            request_id=request_id,
            chat_session_id=chat_session_id,
            execution_context_id=execution_context_id,
            resume={
                "type": "input",
                "input_request_id": input_request_id,
                "value": value,
            },
        )

    async def resume_approval(
        self,
        *,
        agent_thread_id: str,
        request_id: str,
        chat_session_id: str,
        execution_context_id: str,
        confirmation_id: str,
        decision: str,
        change_target: str | None = None,
    ) -> None:
        """승인/수정/취소로 재개(resume.type=approval).

        FE decision("approve"/"change_requested"/"cancelled")을 Agent
        approval_outcome 으로 번역한다. change_target 은 change_requested 에만 넣는다.
        """
        outcome = _APPROVAL_OUTCOME_BY_DECISION.get(decision)
        if outcome is None:
            raise AgentServiceError(f"알 수 없는 승인 decision: {decision}")
        resume: dict[str, Any] = {
            "type": "approval",
            "confirmation_id": confirmation_id,
            "approval_outcome": outcome,
        }
        if outcome == "change_requested" and change_target is not None:
            resume["change_target"] = change_target
        await self._resume(
            agent_thread_id=agent_thread_id,
            request_id=request_id,
            chat_session_id=chat_session_id,
            execution_context_id=execution_context_id,
            resume=resume,
        )

    async def resume_authentication(
        self,
        *,
        agent_thread_id: str,
        request_id: str,
        chat_session_id: str,
        execution_context_id: str,
        auth_context_id: str,
        auth_status: str,
    ) -> None:
        """추가 인증 결과로 재개(resume.type=authentication).

        인증 원문(비밀번호)은 Backend 까지만 오므로 여기엔 검증 결과 상태
        (verified/failed/cancelled/expired)만 넘긴다(계약 7.2).
        """
        await self._resume(
            agent_thread_id=agent_thread_id,
            request_id=request_id,
            chat_session_id=chat_session_id,
            execution_context_id=execution_context_id,
            resume={
                "type": "authentication",
                "auth_context_id": auth_context_id,
                "auth_status": auth_status,
            },
        )


# ── 프로세스당 단일 인스턴스(lazy) ────────────────────────────────────────────
_client: AgentServiceClient | None = None


def get_agent_client() -> AgentServiceClient:
    """실 Agent 연동 경로에서 재사용하는 단일 클라이언트."""
    global _client
    if _client is None:
        _client = AgentServiceClient(
            base_url=settings.AGENT_SERVICE_URL,
            service_token=settings.BACKEND_SERVICE_TOKEN.get_secret_value(),
        )
    return _client


async def close_agent_client() -> None:
    """lifespan 종료 시 커넥션 풀 정리."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
