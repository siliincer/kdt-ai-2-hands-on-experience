"""타인 송금 워크플로우 end-to-end 흐름 테스트.

전체 그래프(build_graph + MemorySaver)로 interrupt 연쇄와 재개를 검증한다.
전부 LLM 없이 결정적 경로다 (매칭은 키워드 폴백, 파싱은 정규식/키워드).
"""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from agent.data.mock_bank import MOCK_ACCOUNTS
from agent.graph import build_graph
from agent.service import _new_state


@pytest.fixture()
def graph():
    return build_graph(checkpointer=MemorySaver())


_COUNTER = {"n": 0}


def _config():
    _COUNTER["n"] += 1
    return {"configurable": {"thread_id": f"flow-{_COUNTER['n']}"}}


def _prompt(result: dict) -> str:
    return result["__interrupt__"][0].value["prompt"]


def _trace_steps(result: dict) -> list[str]:
    return [t["step"] for t in result.get("execution_trace", [])]


def test_happy_path_full_info(graph):
    """완전 정보 → 승인 → 인증 → 실행. 잔액이 실제로 차감된다."""
    before = MOCK_ACCOUNTS["user_001"][0]["balance"]
    config = _config()

    r = graph.invoke(_new_state("김철수한테 5만원 보내줘", "user_001"), config)
    card = _prompt(r)
    assert "김철수" in card and "50,000" in card and "승인" in card

    r = graph.invoke(Command(resume="승인"), config)
    assert "본인 인증" in _prompt(r)

    r = graph.invoke(Command(resume="인증완료"), config)
    assert "김철수님에게 50,000원을 송금했습니다" in r["final_response"]
    assert MOCK_ACCOUNTS["user_001"][0]["balance"] == before - 50_000

    steps = _trace_steps(r)
    assert steps[:3] == [
        "extract_transfer_slots",
        "check_recipient_input",
        "resolve_recipient_input",
    ]
    assert "run_pre_execution_guardrail" in steps
    assert steps[-1] == "write_audit_log"


def test_missing_info_reask_chain(graph):
    """정보 없는 발화 → 수취인/금액 되묻기 → 승인 → 인증 → 완료."""
    config = _config()

    r = graph.invoke(_new_state("송금해줘", "user_001"), config)
    assert "누구에게" in _prompt(r)

    r = graph.invoke(Command(resume="김철수"), config)
    assert "얼마를" in _prompt(r)

    r = graph.invoke(Command(resume="3만원"), config)
    assert "30,000" in _prompt(r)  # 승인 카드

    r = graph.invoke(Command(resume="승인"), config)
    r = graph.invoke(Command(resume="인증완료"), config)
    assert "30,000원을 송금했습니다" in r["final_response"]


def test_limit_exceeded_blocks_without_interrupt(graph):
    """한도(5천만) 초과는 interrupt 없이 즉시 차단 사유를 응답한다."""
    r = graph.invoke(_new_state("김철수한테 6000만원 보내줘", "user_001"), _config())
    assert "__interrupt__" not in r
    assert "한도" in r["final_response"]
    steps = _trace_steps(r)
    assert "show_transfer_blocked" in steps
    assert steps[-1] == "write_audit_log"


def test_insufficient_balance_reselects_account(graph):
    """잔액 부족 → 계좌 재선택 → 신규 수취인 경고 → 진행."""
    config = _config()

    r = graph.invoke(
        _new_state("생활비통장에서 이영희한테 50만원 보내줘", "user_001"), config
    )
    # 생활비통장 430,000 < 500,000 → 재선택 요청
    assert "부족" in _prompt(r)

    r = graph.invoke(Command(resume="1번"), config)
    # 이영희는 송금 이력 없는 신규 수취인 → new_recipient_warning 경고
    assert "처음 보내는 수취인" in _prompt(r)

    r = graph.invoke(Command(resume="확인"), config)
    card = _prompt(r)
    assert "이영희" in card and "500,000" in card and "입출금통장" in card

    r = graph.invoke(Command(resume="승인"), config)
    r = graph.invoke(Command(resume="인증완료"), config)
    assert "이영희님에게 500,000원을 송금했습니다" in r["final_response"]


def test_cancel_at_approval_keeps_balance(graph):
    """승인 카드에서 취소하면 잔액이 변하지 않는다."""
    before = MOCK_ACCOUNTS["user_001"][0]["balance"]
    config = _config()

    r = graph.invoke(_new_state("김철수한테 5만원 보내줘", "user_001"), config)
    r = graph.invoke(Command(resume="취소"), config)

    assert "취소했습니다" in r["final_response"]
    assert MOCK_ACCOUNTS["user_001"][0]["balance"] == before
    assert "show_transfer_cancelled" in _trace_steps(r)


def test_unknown_reply_at_approval_cancels(graph):
    """승인 게이트의 해석 불가 답변은 보수적으로 취소된다."""
    config = _config()
    graph.invoke(_new_state("김철수한테 5만원 보내줘", "user_001"), config)
    r = graph.invoke(Command(resume="음 글쎄요"), config)
    assert "취소했습니다" in r["final_response"]


def test_edit_amount_loop_revalidates(graph):
    """승인 카드에서 금액 수정 → 재검증 체인 → 새 승인 카드 → 완료."""
    config = _config()

    r = graph.invoke(_new_state("김철수한테 5만원 보내줘", "user_001"), config)
    assert "50,000" in _prompt(r)

    r = graph.invoke(Command(resume="금액 수정"), config)
    assert "새 송금 금액" in _prompt(r)

    r = graph.invoke(Command(resume="10만원"), config)
    card = _prompt(r)
    assert "100,000" in card  # 두 번째 승인 카드

    r = graph.invoke(Command(resume="승인"), config)
    r = graph.invoke(Command(resume="인증완료"), config)
    assert "100,000원을 송금했습니다" in r["final_response"]

    # 수정 후 재검증 체인이 실제로 다시 돌았는지 확인
    steps = _trace_steps(r)
    assert steps.count("verify_amount") >= 2
    assert steps.count("check_balance") >= 2


def test_warning_path_confirm_and_cancel(graph):
    """100만원 이상은 주의 안내를 거친다 (확인 → 진행 / 취소 → 중단)."""
    config = _config()
    r = graph.invoke(_new_state("김철수한테 120만원 보내줘", "user_001"), config)
    assert "주의가 필요한 송금" in _prompt(r)

    r = graph.invoke(Command(resume="확인"), config)
    assert "1,200,000" in _prompt(r)  # 승인 카드로 진행

    r = graph.invoke(Command(resume="승인"), config)
    r = graph.invoke(Command(resume="인증완료"), config)
    assert "1,200,000원을 송금했습니다" in r["final_response"]

    # 취소 변형
    config2 = _config()
    graph.invoke(_new_state("김철수한테 120만원 보내줘", "user_001"), config2)
    r = graph.invoke(Command(resume="취소"), config2)
    assert "취소했습니다" in r["final_response"]


def test_auth_failure_stops_transfer(graph):
    """본인 인증 실패 시 송금이 실행되지 않는다."""
    before = MOCK_ACCOUNTS["user_001"][0]["balance"]
    config = _config()

    graph.invoke(_new_state("김철수한테 5만원 보내줘", "user_001"), config)
    graph.invoke(Command(resume="승인"), config)
    r = graph.invoke(Command(resume="안 할래"), config)

    assert "인증이 완료되지 않아" in r["final_response"]
    assert MOCK_ACCOUNTS["user_001"][0]["balance"] == before


def test_cancel_at_input_step(graph):
    """되묻기(input) 스텝에서도 취소가 동작한다 (엔진 갭 A 검증)."""
    config = _config()
    r = graph.invoke(_new_state("송금해줘", "user_001"), config)
    assert "누구에게" in _prompt(r)

    r = graph.invoke(Command(resume="취소"), config)
    assert "취소했습니다" in r["final_response"]
    assert "show_transfer_cancelled" in _trace_steps(r)
