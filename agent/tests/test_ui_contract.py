"""frontend UI 계약 검증 (시트 UI Spec 탭 기반).

interrupt payload에 실리는 구조화 ui 힌트가 그래프를 통과해
HTTP 응답(ChatResponse.ui)까지 도달하는지 확인한다.
"""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from agent.graph import build_graph
from agent.service import _new_state


@pytest.fixture()
def graph():
    return build_graph(checkpointer=MemorySaver())


_COUNTER = {"n": 0}


def _config():
    _COUNTER["n"] += 1
    return {"configurable": {"thread_id": f"ui-{_COUNTER['n']}"}}


def _payload(result: dict) -> dict:
    return result["__interrupt__"][0].value


def test_balance_account_selection_carries_card_list(graph):
    """계좌 특정 불가 → account_card_list ui (복수 선택)."""
    result = graph.invoke(_new_state("잔액 얼마야?", "user_001"), _config())
    ui = _payload(result)["ui"]

    assert ui["type"] == "account_card_list"
    assert ui["multi"] is True
    assert len(ui["options"]) == 2
    assert {"account_id", "account_name", "balance"} <= set(ui["options"][0])


def test_approval_card_carries_confirm_modal(graph):
    """승인 카드 → confirm_modal (display 5필드 + actions)."""
    result = graph.invoke(_new_state("김철수한테 5만원 보내줘", "user_001"), _config())
    ui = _payload(result)["ui"]

    assert ui["type"] == "confirm_modal"
    assert ui["display"] == {
        "recipient_name": "김철수",
        "bank": "국민은행",
        "account_number": "123-456-789012",
        "from_account_name": "입출금통장",
        "amount": 50_000,
    }
    assert ui["actions"] == [
        "송금하기",
        "취소",
        "수취인 수정",
        "금액 수정",
        "계좌 수정",
    ]


def test_action_label_reply_approves(graph):
    """UI 버튼 라벨('송금하기')이 그대로 회신돼도 승인으로 처리된다."""
    config = _config()
    graph.invoke(_new_state("김철수한테 5만원 보내줘", "user_001"), config)
    result = graph.invoke(Command(resume="송금하기"), config)

    # 승인 통과 → 본인 인증 단계 (auth_request ui)
    ui = _payload(result)["ui"]
    assert ui["type"] == "auth_request"
    assert "인증완료" in ui["actions"]


def test_reask_chain_carries_ui_types(graph):
    """정보 없는 발화: search_select → number_input 순서로 ui가 실린다."""
    config = _config()

    result = graph.invoke(_new_state("송금해줘", "user_001"), config)
    ui = _payload(result)["ui"]
    assert ui["type"] == "search_select"
    assert len(ui["options"]) == 2  # 등록 수취인 2명
    assert {"recipient_id", "name", "bank"} <= set(ui["options"][0])

    result = graph.invoke(Command(resume="김철수"), config)
    assert _payload(result)["ui"]["type"] == "number_input"


def test_consumed_ui_does_not_leak_to_next_interrupt(graph):
    """input 노드가 소비한 prompt_ui가 다음 interrupt에 새지 않는다."""
    config = _config()
    graph.invoke(_new_state("송금해줘", "user_001"), config)  # search_select
    graph.invoke(Command(resume="김철수"), config)  # number_input
    result = graph.invoke(Command(resume="3만원"), config)  # 승인 카드

    ui = _payload(result)["ui"]
    assert ui["type"] == "confirm_modal"  # 이전 number_input이 남아 있으면 실패


def test_all_interrupt_uis_conform_to_schema(graph):
    """대표 시나리오의 모든 interrupt ui가 ChatUi 계약(discriminated union)에
    맞는지 스키마로 강제한다. 계약 밖 필드 구조·타입 변경은 여기서 잡힌다."""
    from pydantic import TypeAdapter

    from agent.schemas import ChatUi

    adapter = TypeAdapter(ChatUi)
    seen_types = set()

    def collect(result):
        if "__interrupt__" in result:
            ui = _payload(result).get("ui")
            if ui is not None:
                validated = adapter.validate_python(ui)
                seen_types.add(validated.type)

    # 잔액조회: account_card_list
    config = _config()
    collect(graph.invoke(_new_state("잔액 얼마야?", "user_001"), config))

    # 송금 되묻기 연쇄: search_select → number_input → confirm_modal(승인)
    config = _config()
    collect(graph.invoke(_new_state("송금해줘", "user_001"), config))
    collect(graph.invoke(Command(resume="김철수"), config))
    collect(graph.invoke(Command(resume="3만원"), config))
    # 승인 → auth_request
    collect(graph.invoke(Command(resume="승인"), config))

    # 고액 경고: confirm_modal(variant=warning)
    config = _config()
    result = graph.invoke(_new_state("김철수한테 120만원 보내줘", "user_001"), config)
    ui = _payload(result)["ui"]
    assert adapter.validate_python(ui).variant == "warning"
    collect(result)

    assert seen_types == {
        "account_card_list",
        "search_select",
        "number_input",
        "confirm_modal",
        "auth_request",
    }


def test_openapi_omits_legacy_chat_ui_contract(client):
    """UI는 Webhook 계약으로 전달하며 구형 ChatResponse는 노출하지 않는다."""
    spec = client.get("/openapi.json").json()
    schemas = spec["components"]["schemas"]
    assert "ChatResponse" not in schemas
    assert "/chat" not in spec["paths"]


def test_legacy_chat_api_cannot_expose_ui(client):
    """구형 /chat UI 응답 경로가 다시 열리는 회귀를 막는다."""
    response = client.post("/chat", json={"message": "김철수한테 5만원 보내줘"})
    assert response.status_code == 404
