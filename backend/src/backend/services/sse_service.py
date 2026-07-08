import asyncio
from collections.abc import AsyncIterable
from uuid import UUID

from fastapi.sse import ServerSentEvent

from ..schemas.sse import AgentStreamEvent, AgentStreamEventType

MOCK_EVENT_SEQUENCE: list[tuple[AgentStreamEventType, str]] = [
    (AgentStreamEventType.STATUS, "SSE 연결이 설정되었습니다."),
    (AgentStreamEventType.STATUS, "Agent 계획 수립 중..."),
    (AgentStreamEventType.TOOL_CALL, "get_balance 도구 호출 중..."),
    (AgentStreamEventType.STATUS, "잔고 조회 완료"),
    (AgentStreamEventType.DONE, "Phase 1 Mock 스트림이 완료되었습니다."),
]

MOCK_EVENT_INTERVAL_SECONDS = 2.0


async def mock_agent_stream(user_id: UUID) -> AsyncIterable[ServerSentEvent]:
    """Phase 1: Redis Stream 없이 고정 이벤트를 순차 전송하는 Mock SSE 제너레이터."""
    yield ServerSentEvent(comment=f"mock-stream user_id={user_id}")

    for index, (event_type, content) in enumerate(MOCK_EVENT_SEQUENCE, start=1):
        if index > 1:
            await asyncio.sleep(MOCK_EVENT_INTERVAL_SECONDS)

        payload = AgentStreamEvent(event_type=event_type, content=content)
        yield ServerSentEvent(
            data=payload,
            event=event_type.value,
            id=str(index),
        )

        if event_type == AgentStreamEventType.DONE:
            yield ServerSentEvent(raw_data="[DONE]", event="done")
            break
