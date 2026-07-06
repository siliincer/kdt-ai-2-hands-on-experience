"""채팅 실행 서비스.

fin-ai 원본의 CLI 진입점(main.py의 ask/chat)을 HTTP 대화 프로토콜로 대체한 계층.

동작 방식:
  - 새 턴: 매번 새 thread_id로 그래프를 실행한다. (원본 ask()와 동일 —
    이전 턴의 final_response/prompt_message 등 상태 잔존을 방지한다.)
  - 재개 턴: 클라이언트가 thread_id를 보내고 해당 스레드에 pending interrupt가
    있으면 Command(resume=답변)으로 이어서 실행한다.
  - pending interrupt가 없는 thread_id가 오면 조용히 새 턴으로 처리한다.

제약: MemorySaver는 프로세스 내 메모리라 단일 워커 전제이며, 서버 재시작 시
대기 중이던 interrupt 세션이 사라진다.
자세한 내용은 agent/docs/agent-integration.md 참조.
"""

from __future__ import annotations

import uuid

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from agent.graph import build_graph

GRAPH = build_graph(checkpointer=MemorySaver())

# 그래프 status → API status 매핑 (그 외 값은 failed 처리)
_STATUS_MAP = {
    "completed": "completed",
    "blocked": "blocked",
    "no_match": "no_match",
}


def _new_state(message: str, user_id: str) -> dict:
    """새 턴의 초기 상태."""
    return {
        "user_id": user_id,
        "user_input": message,
        "status": "start",
        "data": {},
        "logs": [],
        "execution_trace": [],
    }


def _has_pending_interrupt(thread_id: str) -> bool:
    """해당 스레드가 interrupt로 멈춰 사용자 입력을 기다리는 중인지 확인한다."""
    snapshot = GRAPH.get_state({"configurable": {"thread_id": thread_id}})
    return bool(snapshot.next) and bool(snapshot.interrupts)


def run_chat(message: str, user_id: str, thread_id: str | None) -> dict:
    """한 턴을 실행하고 ChatResponse 형태의 dict를 반환한다."""
    if thread_id and _has_pending_interrupt(thread_id):
        config = {"configurable": {"thread_id": thread_id}}
        result = GRAPH.invoke(Command(resume=message), config=config)
    else:
        thread_id = uuid.uuid4().hex
        config = {"configurable": {"thread_id": thread_id}}
        result = GRAPH.invoke(_new_state(message, user_id), config=config)

    interrupts = result.get("__interrupt__")
    if interrupts:
        payload = interrupts[0].value or {}
        return {
            "reply": payload.get("prompt") or "선택해 주세요.",
            "status": "waiting_input",
            "thread_id": thread_id,
            "prompt_for": payload.get("prompt_for"),
            "ui": payload.get("ui"),
        }

    return {
        "reply": result.get("final_response") or "요청 처리에 실패했습니다.",
        "status": _STATUS_MAP.get(result.get("status"), "failed"),
        "thread_id": thread_id,
        "prompt_for": None,
        "ui": None,
    }
