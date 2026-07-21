"""계좌 목록 조회(wf_account_list) tool 단위 테스트.

그래프 없이 함수를 직접 호출한다. conftest가 로컬 원장 + API 키 제거를 보장한다.
"""

from __future__ import annotations

from agent.tools.bank_tools import (
    fetch_account_list,
    generate_account_list_response,
)
from agent.tools.registry import TOOL_REGISTRY


def test_registered():
    assert TOOL_REGISTRY["fetch_account_list"] is fetch_account_list
    assert TOOL_REGISTRY["generate_account_list_response"] is generate_account_list_response


def test_fetch_returns_accounts_and_success():
    result = fetch_account_list({"user_id": "user_001", "data": {}})
    assert result["route_key"] == "success"
    accounts = result["account.list"]
    assert len(accounts) >= 1
    # 필요한 필드가 다 있어야 응답 생성이 된다
    for a in accounts:
        assert {"account_id", "account_name", "balance"} <= set(a)


def test_fetch_empty_for_unknown_user():
    result = fetch_account_list({"user_id": "nobody", "data": {}})
    assert result["route_key"] == "empty"
    assert result["account.list"] == []


def test_generate_response_lists_accounts():
    items = [
        {"account_id": "a1", "account_name": "입출금통장", "balance": 1_250_000},
        {"account_id": "a2", "account_name": "생활비통장", "balance": 430_000},
    ]
    result = generate_account_list_response({"data": {"account.list": items}})
    assert result["route_key"] == "success"
    reply = result["final_response"]
    assert "입출금통장" in reply and "생활비통장" in reply
    assert "1,250,000" in reply  # 천단위 구분 + 수치 왜곡 없음


def test_generate_response_empty_is_failed():
    result = generate_account_list_response({"data": {"account.list": []}})
    assert result["route_key"] == "failed"
