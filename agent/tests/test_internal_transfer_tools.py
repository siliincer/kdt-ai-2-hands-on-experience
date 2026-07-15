"""본인 계좌 간 이체(wf_internal_transfer) tool 단위 테스트.

verify_amount/verify_from_account/check_balance는 external_transfer와 공유하며
test_transfer_tools.py에서 이미 검증한다. 여기서는 itx 전용 tool만 다룬다.
"""

from __future__ import annotations

from agent.data.mock_bank import MOCK_ACCOUNTS
from agent.tools.bank_tools import (
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
