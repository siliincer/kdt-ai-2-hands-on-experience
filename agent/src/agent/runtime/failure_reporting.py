"""처리되지 않은 Agent Workflow 오류를 Backend에 안전하게 알린다."""

from __future__ import annotations

from agent.clients.backend import BackendWebhookClient
from agent.runtime.webhook_events import InteractionWebhookBuilder

GLOBAL_WORKFLOW_ID = "wf_global_agent_entry"
FAILURE_STEP_ID = "emit_workflow_dispatch_error"
FAILURE_UI_CONTRACT_ID = "UI-COMMON-ERROR"
SAFE_FAILURE_MESSAGE = "요청 처리 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요."


class WebhookExecutionFailureReporter:
    """공통 오류 UI 계약으로 실행 실패 Webhook을 한 번 전송한다."""

    def __init__(
        self,
        webhook_client: BackendWebhookClient,
        webhook_builder: InteractionWebhookBuilder,
    ) -> None:
        self._webhook_client = webhook_client
        self._webhook_builder = webhook_builder

    async def report_failure(
        self,
        *,
        agent_thread_id: str,
        chat_session_id: str,
        execution_context_id: str,
        request_id: str,
    ) -> None:
        del agent_thread_id
        event = self._webhook_builder.error(
            chat_session_id=chat_session_id,
            workflow_id=GLOBAL_WORKFLOW_ID,
            step_id=FAILURE_STEP_ID,
            ui_contract_id=FAILURE_UI_CONTRACT_ID,
            content=SAFE_FAILURE_MESSAGE,
            payload={"message": SAFE_FAILURE_MESSAGE},
        )
        await self._webhook_client.publish(
            event,
            execution_context_id=execution_context_id,
            request_id=request_id,
        )
