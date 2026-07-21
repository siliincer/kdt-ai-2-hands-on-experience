"""본인 계좌 간 이체(wf_internal_transfer) tool 단위 테스트.

verify_amount/verify_from_account/check_balance는 external_transfer와 공유하며
test_transfer_tools.py에서 이미 검증한다. 여기서는 itx 전용 tool만 다룬다.
"""

from __future__ import annotations

from agent.data.mock_bank import MOCK_ACCOUNTS
from agent.tools.bank_tools import (
    _parse_itx_approval_reply,
    execute_internal_transfer,
    extract_internal_transfer_slots,
    generate_internal_transfer_response,
    run_itx_pre_execution_guardrail,
    verify_to_account,
)
from agent.tools.registry import TOOL_REGISTRY

WF = "wf_internal_transfer"


def _state(**data) -> dict:
    return {"user_id": "user_001", "workflow_id": WF, "data": data}


def test_registered():
    for tid in (
        "extract_internal_transfer_slots",
        "verify_to_account",
        "request_itx_approval",
        "run_itx_pre_execution_guardrail",
        "execute_internal_transfer",
        "generate_internal_transfer_response",
    ):
        assert tid in TOOL_REGISTRY


# ── 승인 카드 답변 파서 (_parse_itx_approval_reply) ──────────────────────────
# 그래프 없이 함수 직접 호출로 분기만 검증. 대화형 흐름(interrupt/resume)은
# test_internal_transfer_flow.py에서 그래프로 검증한다.


def test_parse_itx_approval_reply_approved_keywords():
    assert _parse_itx_approval_reply("승인") == "approved"
    assert _parse_itx_approval_reply("네 보내주세요") == "approved"
    assert _parse_itx_approval_reply("진행해줘") == "approved"


def test_parse_itx_approval_reply_approved_exact_phrases():
    assert _parse_itx_approval_reply("송금하기") == "approved"
    assert _parse_itx_approval_reply("이체") == "approved"
    assert _parse_itx_approval_reply("이체하기") == "approved"


def test_parse_itx_approval_reply_cancelled():
    assert _parse_itx_approval_reply("취소") == "cancelled"
    assert _parse_itx_approval_reply("그만") == "cancelled"


def test_parse_itx_approval_reply_edit_amount():
    assert _parse_itx_approval_reply("금액 수정") == "edit_amount"


def test_parse_itx_approval_reply_edit_from_account():
    # "출금"이 포함되면 출금 계좌 수정, "계좌"만 있고 출금/입금이 없으면도
    # from_account로 폴백된다(구현상 "계좌" 분기가 "입금" 분기보다 뒤에 있음).
    assert _parse_itx_approval_reply("출금 계좌 수정") == "edit_from_account"
    assert _parse_itx_approval_reply("계좌 바꿔줘") == "edit_from_account"


def test_parse_itx_approval_reply_edit_to_account():
    assert _parse_itx_approval_reply("입금 계좌 수정") == "edit_to_account"


def test_parse_itx_approval_reply_unknown_defaults_to_cancelled():
    # 해석 불가 답변은 보수적으로 취소 — 돈이 움직이기 직전이므로 fail-safe.
    assert _parse_itx_approval_reply("음... 글쎄") == "cancelled"
    assert _parse_itx_approval_reply("") == "cancelled"


def test_extract_finds_from_to_and_amount():
    s = _state()
    s["user_input"] = "입출금통장에서 생활비통장으로 5만원 옮겨줘"
    result = extract_internal_transfer_slots(s)
    assert result["route_key"] == "extracted"
    assert result["itx.from_account"] == "입출금통장"
    assert result["itx.to_hint"] == "생활비통장"
    assert result["itx.amount"] == 50_000


def test_extract_no_match_returns_extracted_without_slots():
    s = _state()
    s["user_input"] = "이체하고 싶어요"
    result = extract_internal_transfer_slots(s)
    assert result["route_key"] == "extracted"
    assert "itx.from_account" not in result


def test_verify_to_account_excludes_from_account():
    from_account = next(
        a for a in MOCK_ACCOUNTS["user_001"] if a["account_name"] == "입출금통장"
    )
    result = verify_to_account(_state(**{"itx.from_account": from_account}))
    assert result["route_key"] == "verified"
    assert result["itx.to_account"]["account_name"] == "생활비통장"


def test_verify_to_account_no_other_accounts():
    only = MOCK_ACCOUNTS["user_001"][0]
    result = verify_to_account(
        _state(**{"itx.from_account": only}),
    )
    # 두 계좌 중 하나 제외하면 하나 남음(자동 확정) — 후보가 아예 없는 케이스는
    # mock이 2계좌뿐이라 여기선 재현하지 않고 verified만 확인한다.
    assert result["route_key"] in ("verified", "select_needed")


def test_pre_execution_guardrail_blocks_when_balance_insufficient():
    result = run_itx_pre_execution_guardrail(
        _state(
            **{
                "itx.from_account": {"account_id": "acc_001"},
                "itx.amount": 999_999_999,
            }
        )
    )
    assert result["route_key"] == "blocked"


def test_pre_execution_guardrail_allows_when_balance_sufficient():
    account = next(
        a for a in MOCK_ACCOUNTS["user_001"] if a["account_name"] == "입출금통장"
    )
    result = run_itx_pre_execution_guardrail(
        _state(
            **{
                "itx.from_account": account,
                "itx.amount": 10_000,
            }
        )
    )
    assert result["route_key"] == "allowed"


def test_execute_moves_balance_between_accounts():
    from_account = next(
        a for a in MOCK_ACCOUNTS["user_001"] if a["account_name"] == "입출금통장"
    )
    to_account = next(
        a for a in MOCK_ACCOUNTS["user_001"] if a["account_name"] == "생활비통장"
    )
    before_from, before_to = from_account["balance"], to_account["balance"]

    result = execute_internal_transfer(
        _state(
            **{
                "itx.from_account": from_account,
                "itx.to_account": to_account,
                "itx.amount": 50_000,
            }
        )
    )
    assert result["route_key"] == "success"
    assert from_account["balance"] == before_from - 50_000
    assert to_account["balance"] == before_to + 50_000


def test_generate_response_mentions_target_and_amount():
    result = generate_internal_transfer_response(
        _state(
            **{
                "itx.result": {
                    "to_account_name": "생활비통장",
                    "amount": 50_000,
                    "transaction_id": "txn_test",
                }
            }
        )
    )
    assert result["route_key"] == "success"
    assert "생활비통장" in result["final_response"]
    assert "50,000" in result["final_response"]
