"""기본 출금계좌 설정(wf_set_default_account) tool 단위 테스트.

그래프 없이 함수를 직접 호출한다. 공유 tool은 workflow_id로 네임스페이스를
알아내므로 state에 workflow_id를 넣는다. conftest가 원장 스냅샷을 복원한다.
"""

from __future__ import annotations

from agent.data.mock_bank import MOCK_ACCOUNTS
from agent.tools.bank_tools import (
    apply_default_account,
    extract_setting_slots,
    generate_setting_response,
    verify_target_account,
)
from agent.tools.registry import TOOL_REGISTRY

WF = "wf_set_default_account"


def _state(**data) -> dict:
    return {"user_id": "user_001", "workflow_id": WF, "data": data}


def test_registered():
    for tid in (
        "extract_setting_slots",
        "verify_target_account",
        "request_setting_approval",
        "apply_default_account",
        "generate_setting_response",
    ):
        assert tid in TOOL_REGISTRY


def test_extract_finds_account_hint():
    s = _state()
    s["user_input"] = "생활비통장을 기본으로 해줘"
    result = extract_setting_slots(s)
    assert result["route_key"] == "extracted"
    assert result["default.account_hint"] == "생활비통장"


def test_verify_target_single_confirmed():
    result = verify_target_account(_state(**{"default.account_hint": "생활비"}))
    assert result["route_key"] == "confirmed"
    assert result["default.account"]["account_name"] == "생활비통장"


def test_verify_target_not_found():
    result = verify_target_account(_state(**{"default.account_hint": "없는계좌"}))
    assert result["route_key"] == "not_found"


def test_apply_sets_default_flag():
    account = next(a for a in MOCK_ACCOUNTS["user_001"] if a["account_name"] == "생활비통장")
    result = apply_default_account(_state(**{"default.account": account}))
    assert result["route_key"] == "success"
    # 대상만 is_default=True, 나머지는 False
    for a in MOCK_ACCOUNTS["user_001"]:
        assert a["is_default"] == (a["account_name"] == "생활비통장")


def test_generate_response():
    result = generate_setting_response(_state(**{"default.result": {"account_name": "생활비통장"}}))
    assert result["route_key"] == "success"
    assert "생활비통장" in result["final_response"]
    assert "기본 출금계좌" in result["final_response"]
