"""계좌 별칭 설정(wf_set_account_alias) tool 단위 테스트.

extract_setting_slots/verify_target_account/generate_setting_response는
set_default_account와 공유하며 test_setting_tools.py에서 이미 검증한다.
여기서는 별칭 전용 분기(별칭 값 추출, apply_account_alias)만 다룬다.
"""

from __future__ import annotations

from agent.data.mock_bank import MOCK_ACCOUNTS
from agent.tools.bank_tools import (
    apply_account_alias,
    extract_setting_slots,
    generate_setting_response,
)
from agent.tools.registry import TOOL_REGISTRY

WF = "wf_set_account_alias"


def _state(**data) -> dict:
    return {"user_id": "user_001", "workflow_id": WF, "data": data}


def test_registered():
    assert TOOL_REGISTRY["apply_account_alias"] is apply_account_alias


def test_extract_finds_hint_and_alias_value():
    s = _state()
    s["user_input"] = "입출금통장을 생활비라고 해줘"
    result = extract_setting_slots(s)
    assert result["route_key"] == "extracted"
    assert result["alias.account_hint"] == "입출금통장"
    assert result["alias.value"] == "생활비"


def test_extract_alias_value_missing_when_pattern_absent():
    s = _state()
    s["user_input"] = "입출금통장 별칭 뭐야"  # "~라고 해" 패턴 없음
    result = extract_setting_slots(s)
    assert "alias.value" not in result


def test_apply_sets_alias_field():
    account = next(a for a in MOCK_ACCOUNTS["user_001"] if a["account_name"] == "입출금통장")
    result = apply_account_alias(_state(**{"alias.account": account, "alias.value": "생활비"}))
    assert result["route_key"] == "success"
    assert result["alias.result"]["alias"] == "생활비"
    target = next(a for a in MOCK_ACCOUNTS["user_001"] if a["account_name"] == "입출금통장")
    assert target["alias"] == "생활비"


def test_apply_missing_value_errors():
    account = MOCK_ACCOUNTS["user_001"][0]
    result = apply_account_alias(_state(**{"alias.account": account}))
    assert result["route_key"] == "error"


def test_generate_response_mentions_alias_value():
    result = generate_setting_response(_state(**{"alias.result": {"account_name": "입출금통장", "alias": "생활비"}}))
    assert result["route_key"] == "success"
    assert "입출금통장" in result["final_response"]
    assert "생활비" in result["final_response"]
