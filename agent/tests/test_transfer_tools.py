"""타인 송금 tool 단위 테스트 (그래프 없이 함수 직접 호출).

대화형 tool(create_approval 등)은 interrupt를 호출하므로 여기서는 다루지 않고
답변 파서만 검증한다. 대화형 흐름은 test_transfer_flow.py에서 그래프로 검증한다.
"""

from __future__ import annotations

from agent.data.mock_bank import MOCK_ACCOUNTS
from agent.tools.bank_tools import (
    _is_cancel,
    _parse_amount,
    _parse_approval_reply,
    _parse_auth_reply,
    _parse_warning_reply,
    _resolve_from_account,
    _resolve_recipient,
    check_amount_input,
    check_balance,
    check_recipient_input,
    extract_transfer_slots,
    generate_transfer_response,
    resolve_recipient_input,
    run_pre_execution_guardrail,
    run_transfer_guardrail,
    transfer_money,
    verify_amount,
    verify_from_account,
    verify_recipient_account,
)


def _state(user_id="user_001", **data) -> dict:
    return {"user_id": user_id, "data": data}


# ── 파서 헬퍼 ─────────────────────────────────────────────────────────────────


def test_parse_amount_formats():
    assert _parse_amount("5만원") == 50_000
    assert _parse_amount("5만") == 50_000
    assert _parse_amount("50,000원") == 50_000
    assert _parse_amount("50000") == 50_000
    assert _parse_amount(50_000) == 50_000
    assert _parse_amount(50_000.0) == 50_000
    assert _parse_amount("얼마였더라") is None
    assert _parse_amount(None) is None
    assert _parse_amount(-100) is None


def test_cancel_keywords():
    assert _is_cancel("취소")
    assert _is_cancel("그만")
    # 정정 답변은 취소가 아니다
    assert not _is_cancel("아니 3만원으로 해줘")


def test_parse_approval_reply():
    assert _parse_approval_reply("승인") == "approved"
    assert _parse_approval_reply("네 보내주세요") == "approved"
    assert _parse_approval_reply("취소") == "cancelled"
    assert _parse_approval_reply("수취인 수정") == "edit_recipient"
    assert _parse_approval_reply("금액 수정") == "edit_amount"
    assert _parse_approval_reply("계좌 수정") == "edit_from_account"
    # 해석 불가 답변은 보수적으로 취소
    assert _parse_approval_reply("음... 글쎄") == "cancelled"


def test_parse_auth_reply():
    assert _parse_auth_reply("인증완료") == "authenticated"
    assert _parse_auth_reply("완료했어") == "authenticated"
    assert _parse_auth_reply("취소") == "not_authenticated"
    assert _parse_auth_reply("인증 실패") == "not_authenticated"
    assert _parse_auth_reply("몰라") == "not_authenticated"


def test_parse_warning_reply():
    assert _parse_warning_reply("확인") == "confirmed"
    assert _parse_warning_reply("진행해줘") == "confirmed"
    assert _parse_warning_reply("취소") == "cancelled"


def test_resolve_recipient_by_name_and_account():
    resolved, matches = _resolve_recipient("user_001", "김철수")
    assert resolved["recipient_id"] == "rec_001"
    resolved, _ = _resolve_recipient("user_001", "123-456-789012")
    assert resolved["recipient_id"] == "rec_001"
    resolved, matches = _resolve_recipient("user_001", "박없음")
    assert resolved is None
    assert matches == []
    # 이미 확정된 dict는 그대로 통과 (멱등)
    already = {"recipient_id": "rec_x", "name": "a", "bank": "b", "account_number": "1"}
    resolved, _ = _resolve_recipient("user_001", already)
    assert resolved is already


def test_resolve_from_account_variants():
    accounts = MOCK_ACCOUNTS["user_001"]
    # None → 기본 계좌
    resolved, _ = _resolve_from_account("user_001", None)
    assert resolved["account_id"] == "acc_001"
    # "1번" → 첫 계좌
    resolved, _ = _resolve_from_account("user_001", "2번")
    assert resolved["account_id"] == "acc_002"
    # 이름 힌트
    resolved, _ = _resolve_from_account("user_001", "생활비")
    assert resolved["account_id"] == "acc_002"
    # dict → 실시간 재조회 결과 (같은 계좌)
    resolved, _ = _resolve_from_account("user_001", dict(accounts[0]))
    assert resolved is accounts[0]
    # 매칭 실패 → None + 후보
    resolved, candidates = _resolve_from_account("user_001", "없는통장")
    assert resolved is None
    assert len(candidates) == 2


# ── 슬롯 추출 / 입력 확인 ──────────────────────────────────────────────────────


class _FakeSlotLlm:
    """extract_transfer_slots의 LLM 경로 검증용 가짜 LLM."""

    def __init__(self, slots):
        self._slots = slots

    def with_structured_output(self, schema):
        return self

    def invoke(self, prompt):
        return self._slots


def test_extract_transfer_slots_llm_first(monkeypatch):
    """LLM이 1순위 — 정규식으로는 못 뽑는 값도 LLM이 주면 채택된다.

    금액은 LLM이 원 단위 정수로 환산한다 ('오만원' 같은 한글 수사 대응).
    """
    from agent.tools import bank_tools
    from agent.tools.bank_tools import _TransferSlots

    # "오만원만 부쳐줘" 시나리오: LLM이 50000으로 환산해 반환
    fake = _FakeSlotLlm(
        _TransferSlots(recipient="박영수", amount=50_000, from_account_hint="생활비")
    )
    monkeypatch.setattr(bank_tools, "get_llm", lambda *a, **k: fake)

    # "박영수" / 50000은 이 발화의 정규식 매칭으로는 나올 수 없는 값
    result = extract_transfer_slots(
        {"user_input": "지난번 그 사람한테 오만원만 부쳐줘"}
    )
    assert result["transfer.recipient"] == "박영수"
    assert result["transfer.amount"] == 50_000
    assert result["transfer.from_account"] == "생활비"

    # 정수 금액은 verify_amount를 그대로 통과한다
    got = verify_amount(_state(**{"transfer.amount": 50_000}))
    assert got["route_key"] == "valid"
    assert got["transfer.amount"] == 50_000


def test_extract_transfer_slots_ignores_nonpositive_llm_amount(monkeypatch):
    """LLM이 0 이하 금액을 주면 미추출로 취급하고 규칙 폴백을 시도한다."""
    from agent.tools import bank_tools
    from agent.tools.bank_tools import _TransferSlots

    fake = _FakeSlotLlm(
        _TransferSlots(recipient="김철수", amount=0, from_account_hint=None)
    )
    monkeypatch.setattr(bank_tools, "get_llm", lambda *a, **k: fake)

    result = extract_transfer_slots({"user_input": "김철수한테 5만원 보내줘"})
    assert result["transfer.amount"] == 50_000  # 정규식 폴백이 채움


def test_extract_transfer_slots_partial_llm_backfilled_by_rule(monkeypatch):
    """LLM이 일부 슬롯만 주면 나머지는 규칙(정규식)으로 보강된다."""
    from agent.tools import bank_tools
    from agent.tools.bank_tools import _TransferSlots

    fake = _FakeSlotLlm(
        _TransferSlots(recipient="김철수", amount=None, from_account_hint=None)
    )
    monkeypatch.setattr(bank_tools, "get_llm", lambda *a, **k: fake)

    result = extract_transfer_slots(
        {"user_input": "생활비통장에서 김철수한테 5만원 보내줘"}
    )
    assert result["transfer.recipient"] == "김철수"  # LLM 값
    assert result["transfer.amount"] == 50_000  # 정규식 보강
    assert result["transfer.from_account"] == "생활비"  # 정규식 보강


def test_extract_transfer_slots_full_utterance():
    result = extract_transfer_slots(
        {"user_input": "생활비통장에서 김철수한테 5만원 보내줘"}
    )
    assert result["transfer.recipient"] == "김철수"
    assert result["transfer.amount"] == 50_000
    assert result["transfer.from_account"] == "생활비"
    assert result["route_key"] == "success"


def test_extract_transfer_slots_empty_utterance():
    result = extract_transfer_slots({"user_input": "송금해줘"})
    assert result["transfer.recipient"] is None
    assert result["transfer.amount"] is None
    assert result["route_key"] == "success"


def test_check_inputs():
    assert check_recipient_input(_state())["route_key"] == "missing"
    got = check_recipient_input(_state(**{"transfer.recipient": "김철수"}))
    assert got["route_key"] == "exists"
    assert check_amount_input(_state())["route_key"] == "missing"
    got = check_amount_input(_state(**{"transfer.amount": 50_000}))
    assert got["route_key"] == "exists"


def test_resolve_and_verify_recipient():
    got = resolve_recipient_input(_state(**{"transfer.recipient": "김철수"}))
    assert got["route_key"] == "resolved"
    assert got["transfer.recipient"]["bank"] == "국민은행"

    got = resolve_recipient_input(_state(**{"transfer.recipient": "박없음"}))
    assert got["route_key"] == "failed"
    assert "등록된 수취인" in got["prompt_message"]

    # 문자열 직접 검증 (ask_recipient 직행 경로)
    got = verify_recipient_account(_state(**{"transfer.recipient": "이영희"}))
    assert got["route_key"] == "verified"
    got = verify_recipient_account(_state(**{"transfer.recipient": "박없음"}))
    assert got["route_key"] == "not_verified"


# ── 검증 ──────────────────────────────────────────────────────────────────────


def test_verify_amount_routes():
    got = verify_amount(_state(**{"transfer.amount": "5만원"}))
    assert got["route_key"] == "valid"
    assert got["transfer.amount"] == 50_000

    assert verify_amount(_state(**{"transfer.amount": "몰라"}))["route_key"] == (
        "invalid"
    )

    got = verify_amount(_state(**{"transfer.amount": 60_000_000}))
    assert got["route_key"] == "limit_exceeded"
    assert "한도" in got["final_response"]


def test_verify_from_account_routes():
    got = verify_from_account(_state())
    assert got["route_key"] == "verified"  # 기본 계좌
    assert got["transfer.from_account"]["account_id"] == "acc_001"

    got = verify_from_account(_state(**{"transfer.from_account": "없는통장"}))
    assert got["route_key"] == "needs_selection"
    assert "어느 계좌" in got["prompt_message"]


def test_check_balance_routes():
    account = MOCK_ACCOUNTS["user_001"][1]  # 생활비통장 430,000
    got = check_balance(
        _state(**{"transfer.amount": 500_000, "transfer.from_account": account})
    )
    assert got["route_key"] == "insufficient"

    got = check_balance(
        _state(**{"transfer.amount": 100_000, "transfer.from_account": account})
    )
    assert got["route_key"] == "sufficient"

    # 실시간 재조회: state 복사본이 아니라 원장 잔액 기준
    stale = dict(account)
    stale["balance"] = 999_999_999
    got = check_balance(
        _state(**{"transfer.amount": 500_000, "transfer.from_account": stale})
    )
    assert got["route_key"] == "insufficient"


def test_run_transfer_guardrail_thresholds():
    assert (
        run_transfer_guardrail(_state(**{"transfer.amount": 50_000}))["route_key"]
        == "allowed"
    )
    got = run_transfer_guardrail(_state(**{"transfer.amount": 1_200_000}))
    assert got["route_key"] == "warning_required"
    got = run_transfer_guardrail(_state(**{"transfer.amount": 10_000_000}))
    assert got["route_key"] == "blocked"
    assert "정책상" in got["final_response"]


def test_pre_execution_guardrail():
    recipient = MOCK_ACCOUNTS and {
        "recipient_id": "rec_001",
        "name": "김철수",
        "bank": "국민은행",
        "account_number": "123-456-789012",
    }
    account = MOCK_ACCOUNTS["user_001"][0]
    approval = {
        "recipient_id": "rec_001",
        "account_number": "123-456-789012",
        "from_account_id": "acc_001",
        "amount": 50_000,
    }
    base = {
        "transfer.recipient": recipient,
        "transfer.from_account": account,
        "transfer.amount": 50_000,
        "transfer.approval": approval,
    }
    assert run_pre_execution_guardrail(_state(**base))["route_key"] == "allowed"

    # 승인 후 금액이 바뀌면 차단
    tampered = {**base, "transfer.amount": 90_000}
    got = run_pre_execution_guardrail(_state(**tampered))
    assert got["route_key"] == "blocked"

    # 승인 요약 없음 → 차단
    missing = {k: v for k, v in base.items() if k != "transfer.approval"}
    assert run_pre_execution_guardrail(_state(**missing))["route_key"] == "blocked"


# ── 실행 / 응답 ───────────────────────────────────────────────────────────────


def test_transfer_money_deducts_balance():
    account = MOCK_ACCOUNTS["user_001"][0]
    before = account["balance"]
    recipient = {
        "recipient_id": "rec_001",
        "name": "김철수",
        "bank": "국민은행",
        "account_number": "123-456-789012",
    }
    got = transfer_money(
        _state(
            **{
                "transfer.recipient": recipient,
                "transfer.from_account": dict(account),
                "transfer.amount": 50_000,
            }
        )
    )
    assert got["route_key"] == "success"
    assert account["balance"] == before - 50_000
    result = got["transfer.transfer_result"]
    assert result["status"] == "completed"
    assert result["to_recipient_name"] == "김철수"


def test_transfer_money_guards():
    got = transfer_money(_state())
    assert got["route_key"] == "failed"


def test_generate_transfer_response():
    got = generate_transfer_response(
        _state(
            **{
                "transfer.transfer_result": {
                    "transaction_id": "txn_test",
                    "to_recipient_name": "김철수",
                    "amount": 50_000,
                    "status": "completed",
                }
            }
        )
    )
    assert got["route_key"] == "success"
    assert "김철수님에게 50,000원을 송금했습니다" in got["final_response"]

    assert generate_transfer_response(_state())["route_key"] == "failed"
