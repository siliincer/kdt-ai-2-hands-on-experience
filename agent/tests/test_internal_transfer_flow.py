"""본인 계좌 간 이체(wf_internal_transfer) 워크플로우 end-to-end 흐름 테스트.

전체 그래프(build_graph + MemorySaver)로 interrupt 연쇄와 재개를 검증한다.
test_transfer_flow.py(타인송금)의 그래프 레벨 대응 파일 — 다른 점:
  - review_internal_transfer(승인) 이후 본인 인증(auth) 스텝이 없다
    (본인 계좌 간 이동이라 타인송금과 달리 별도 인증 불필요, config/workflows.yaml
    wf_internal_transfer 라우팅 참고).
  - run_pre_execution_guardrail이 승인보다 *먼저* 실행된다(check_balance 직후,
    review_internal_transfer 이전) — bank_tools.run_itx_pre_execution_guardrail
    독스트링 참고.
전부 LLM 없이 결정적 경로다.
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
    return {"configurable": {"thread_id": f"itx-flow-{_COUNTER['n']}"}}


def _prompt(result: dict) -> str:
    return result["__interrupt__"][0].value["prompt"]


def _trace_steps(result: dict) -> list[str]:
    return [t["step"] for t in result.get("execution_trace", [])]


def _accounts():
    checking = next(
        a for a in MOCK_ACCOUNTS["user_001"] if a["account_name"] == "입출금통장"
    )
    living = next(
        a for a in MOCK_ACCOUNTS["user_001"] if a["account_name"] == "생활비통장"
    )
    return checking, living


def test_happy_path_full_info(graph):
    """완전 정보(출금/입금 계좌+금액 다 포함) → 승인 → 실행. 인증 스텝 없음."""
    checking, living = _accounts()
    before_checking, before_living = checking["balance"], living["balance"]
    config = _config()

    r = graph.invoke(
        _new_state("입출금통장에서 생활비통장으로 5만원 옮겨줘", "user_001"), config
    )
    card = _prompt(r)
    assert "입출금통장" in card and "생활비통장" in card and "50,000" in card

    r = graph.invoke(Command(resume="승인"), config)
    assert "생활비통장" in r["final_response"]
    assert "50,000" in r["final_response"]
    assert checking["balance"] == before_checking - 50_000
    assert living["balance"] == before_living + 50_000

    steps = _trace_steps(r)
    assert steps[0] == "extract_internal_transfer_slots"
    assert "run_pre_execution_guardrail" in steps
    # 인증(authenticate) 스텝이 존재하지 않는다 — 본인이체 고유 특성
    assert not any("auth" in s for s in steps)
    assert steps[-1] == "write_audit_log"


def test_cancel_at_approval_keeps_balance(graph):
    """승인 카드에서 취소하면 두 계좌 잔액 모두 변하지 않는다."""
    checking, living = _accounts()
    before_checking, before_living = checking["balance"], living["balance"]
    config = _config()

    r = graph.invoke(
        _new_state("입출금통장에서 생활비통장으로 5만원 옮겨줘", "user_001"), config
    )
    r = graph.invoke(Command(resume="취소"), config)

    assert "취소" in r["final_response"]
    assert checking["balance"] == before_checking
    assert living["balance"] == before_living
    assert "show_itx_cancelled" in _trace_steps(r)


def test_unknown_reply_at_approval_cancels(graph):
    """승인 게이트의 해석 불가 답변은 보수적으로 취소된다.

    (_parse_itx_approval_reply 기본값)
    """
    config = _config()
    graph.invoke(
        _new_state("입출금통장에서 생활비통장으로 5만원 옮겨줘", "user_001"), config
    )
    r = graph.invoke(Command(resume="음... 글쎄요"), config)
    assert "취소" in r["final_response"]


@pytest.mark.xfail(
    reason=(
        "버그: config/workflows.yaml의 wf_internal_transfer에서 "
        "ask_amount --(submitted)--> check_balance로 직결되어 있어 "
        "verify_amount(텍스트 → 정수 파싱)를 안 거친다. wf_external_transfer는 "
        "ask_amount --(submitted)--> verify_amount로 배선되어 있어 정상 동작함 "
        "(test_transfer_flow.py::test_edit_amount_loop_revalidates 대응 테스트 참고). "
        "결과적으로 수정한 금액이 '10만원' 같은 raw 문자열 그대로 itx.amount에 "
        "들어가 check_balance가 '잔액 확인 중 문제가 발생했습니다'로 실패한다. "
        "시트에서 wf_internal_transfer의 ask_amount 성공 라우팅을 "
        "verify_amount로 고치고 재생성하면 해결됨 — 이 파일은 손으로 안 고침"
        "(팀 컨벤션, agent/README.md 3절 참고)."
    ),
    strict=True,
)
def test_edit_amount_loop_revalidates(graph):
    """승인 카드 금액수정 → 재검증(check_balance 재실행) → 새 승인 카드 → 완료.

    타인송금(test_transfer_flow.py::test_edit_amount_loop_revalidates)과
    동일하게 동작해야 하는 게 기대치 — 현재는 버그로 실패한다(위 xfail reason 참고).
    """
    checking, living = _accounts()
    before_checking, before_living = checking["balance"], living["balance"]
    config = _config()

    r = graph.invoke(
        _new_state("입출금통장에서 생활비통장으로 5만원 옮겨줘", "user_001"), config
    )
    assert "50,000" in _prompt(r)

    r = graph.invoke(Command(resume="금액 수정"), config)
    assert "금액" in _prompt(r)

    r = graph.invoke(Command(resume="10만원"), config)
    card = _prompt(r)
    assert "100,000" in card  # 새 승인 카드

    r = graph.invoke(Command(resume="승인"), config)
    assert "100,000" in r["final_response"]
    assert checking["balance"] == before_checking - 100_000
    assert living["balance"] == before_living + 100_000

    # 수정 후 재검증 체인이 실제로 다시 돌았는지 확인 (check_balance가 shared
    # tool이라 external_transfer 플로우와 같은 이름으로 트레이스에 남는다)
    steps = _trace_steps(r)
    assert steps.count("check_balance") >= 2


def test_cancel_at_input_step(graph):
    """정보 부족 → 되묻기 단계에서도 취소가 동작한다."""
    config = _config()
    r = graph.invoke(_new_state("이체하고 싶어요", "user_001"), config)
    # extract 단계에서 슬롯을 못 채우면 verify_from_account가 되묻는다
    assert "__interrupt__" in r

    r = graph.invoke(Command(resume="취소"), config)
    assert "취소" in r["final_response"]
    assert "show_itx_cancelled" in _trace_steps(r)
