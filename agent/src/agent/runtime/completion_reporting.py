"""정상 종료한 Agent 실행 턴을 Backend에 알린다."""

from __future__ import annotations

from agent.clients.backend import BackendWebhookClient
from agent.contracts.backend import AgentWebhookRequest


class WebhookExecutionCompletionReporter:
    """Frontend Stream을 닫을 수 있도록 terminal `done`을 한 번 전송한다."""

    def __init__(self, webhook_client: BackendWebhookClient) -> None:
        self._webhook_client = webhook_client

    async def report_completion(
        self,
        *,
        agent_thread_id: str,
        chat_session_id: str,
        execution_context_id: str,
        request_id: str,
    ) -> str:
        del agent_thread_id
        event = AgentWebhookRequest(
            chat_session_id=chat_session_id,
            event_type="done",
            content="",
            metadata={},
        )
        return await self._webhook_client.publish(
            event,
            execution_context_id=execution_context_id,
            request_id=request_id,
        )
