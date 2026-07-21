"""로컬 테스트용 목 Agent 프로듀서.

실제 Agent(agent/ 폴더)가 아직 스텁이므로, 이 스크립트가 Agent를 흉내내어
agent:stream:{chat_session_id} 로 직접 XADD 한다. mermaid 다이어그램의
`Agent -->|XADD progress| Redis` 경로를 로컬에서 재현하는 용도.

사용법:
    # 1) 티켓 발급으로 chat_session_id 를 먼저 받은 뒤
    # http://localhost:8000/api/v1/sse/ticket bearer <access token>
    cd backend && uv run python scripts/mock_agent_producer.py <chat_session_id>

    # 2) 동시에 다른 터미널에서 SSE 연결 -> sse 출력 확인
    curl -N "http://localhost:8000/api/v1/sse/connect?sse_session_id=<sse_session_id>"

웹훅 경로(POST /api/v1/webhooks/agent)를 테스트하려면 이 스크립트 대신
curl 로 웹훅을 호출하면 된다(둘 다 동일한 스트림에 XADD).
"""

import asyncio
import sys
from uuid import UUID

import redis.asyncio as aioredis

from backend.core.load_environment_var import settings
from backend.schemas.sse import AgentStreamEvent, AgentStreamEventType
from backend.services.agent_stream_producer import publish_agent_event

MOCK_SEQUENCE: list[tuple[AgentStreamEventType, str]] = [
    (AgentStreamEventType.STATUS, "Agent 계획 수립 중..."),
    (AgentStreamEventType.TOOL_CALL, "get_balance 도구 호출 중..."),
    (AgentStreamEventType.STATUS, "잔고 조회 완료"),
    (AgentStreamEventType.NEED_APPROVAL, "송금을 승인하시겠습니까?"),
    (AgentStreamEventType.DONE, "Mock Agent 스트림이 완료되었습니다."),
]
INTERVAL_SECONDS = 2.0


async def main(chat_session_id: UUID) -> None:
    redis_stream = aioredis.from_url(str(settings.REDIS_STREAM_URL).strip(), decode_responses=True)
    try:
        for index, (event_type, content) in enumerate(MOCK_SEQUENCE, start=1):
            approval_id = "appv_mock_001" if event_type == AgentStreamEventType.NEED_APPROVAL else None
            event = AgentStreamEvent(event_type=event_type, content=content, approval_id=approval_id)
            message_id = await publish_agent_event(redis_stream, chat_session_id, event)
            print(f"[XADD #{index}] {event_type.value}: {content} -> {message_id}")
            if index < len(MOCK_SEQUENCE):
                await asyncio.sleep(INTERVAL_SECONDS)
    finally:
        await redis_stream.aclose()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python scripts/mock_agent_producer.py <chat_session_id>")
        raise SystemExit(1)
    asyncio.run(main(UUID(sys.argv[1])))
