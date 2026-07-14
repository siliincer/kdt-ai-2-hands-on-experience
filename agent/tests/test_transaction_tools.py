"""거래내역 조회(wf_transaction_history) / 기간 지출·입금 합계
(wf_period_amount_summary) tool 단위 테스트.

normalize_period/resolve_account_scope/fetch_transactions는 두 워크플로우가
공유하며 여기서 함께 검증한다. extract_*/sum_transactions/generate_*_response는
워크플로우 전용이라 각자 검증한다.
"""

from __future__ import annotations

from agent.tools.bank_tools import (
    extract_amount_summary_slots,
    extract_transaction_slots,
    fetch_transactions,
    generate_amount_summary_response,
    generate_transaction_response,
    normalize_period,
    resolve_account_scope,
    sum_transactions,
)
from agent.tools.registry import TOOL_REGISTRY

TXN = "wf_transaction_history"
SUM = "wf_period_amount_summary"


def _state(wf, **data) -> dict:
    return {"user_id": "user_001", "workflow_id": wf, "data": data}


def test_registered():
    for tid in (
        "extract_transaction_slots",
        "extract_amount_summary_slots",
        "normalize_period",
        "resolve_account_scope",
        "fetch_transactions",
        "generate_transaction_response",
        "sum_transactions",
        "generate_amount_summary_response",
    ):
        assert tid in TOOL_REGISTRY


def test_extract_transaction_finds_period_and_merchant():
    s = _state(TXN)
    s["user_input"] = "이번달 스타벅스 거래내역 보여줘"
    result = extract_transaction_slots(s)
    assert result["route_key"] == "extracted"
    assert result["txn.period_expr"] == "이번달"
    assert result["txn.keyword"] == "스타벅스"


def test_extract_summary_finds_spending_direction():
    s = _state(SUM)
    s["user_input"] = "지난달 얼마 썼어?"
    result = extract_amount_summary_slots(s)
    assert result["sum.period_expr"] == "지난달"
    assert result["sum.txn_type"] == "spending"


def test_extract_summary_finds_income_direction():
    s = _state(SUM)
    s["user_input"] = "이번달 얼마 들어왔어?"
    result = extract_amount_summary_slots(s)
    assert result["sum.txn_type"] == "income"


def test_normalize_period_needs_period_when_missing():
    result = normalize_period(_state(TXN))
    assert result["route_key"] == "needs_period"


def test_normalize_period_this_month():
    result = normalize_period(_state(TXN, **{"txn.period_expr": "이번달"}))
    assert result["route_key"] == "normalized"
    assert "txn.period" in result
    assert result["txn.period"]["from_date"] <= result["txn.period"]["to_date"]


def test_resolve_account_scope_empty_hint_is_all_accounts():
    result = resolve_account_scope(_state(TXN))
    assert result["route_key"] == "all_accounts"


def test_resolve_account_scope_single_match():
    result = resolve_account_scope(_state(TXN, **{"txn.account_hint": "생활비"}))
    assert result["route_key"] == "resolved"
    assert result["txn.account"]["account_name"] == "생활비통장"


def test_fetch_transactions_all_accounts_this_month():
    period = normalize_period(_state(TXN, **{"txn.period_expr": "이번달"}))[
        "txn.period"
    ]
    result = fetch_transactions(_state(TXN, **{"txn.period": period}))
    assert result["route_key"] == "success"
    assert len(result["txn.results"]) == 4  # 이번달 4건 (mock 데이터 기준)


def test_fetch_transactions_filters_by_keyword():
    period = normalize_period(_state(TXN, **{"txn.period_expr": "이번달"}))[
        "txn.period"
    ]
    result = fetch_transactions(
        _state(TXN, **{"txn.period": period, "txn.keyword": "스타벅스"})
    )
    assert result["route_key"] == "success"
    assert all(t["merchant"] == "스타벅스" for t in result["txn.results"])


def test_fetch_transactions_accepts_raw_period_string():
    """ask_period 우회 답변(원시 문자열)도 방어적으로 재해석한다."""
    result = fetch_transactions(_state(TXN, **{"txn.period": "이번달"}))
    assert result["route_key"] in ("success", "empty")


def test_generate_transaction_response_lists_entries():
    result = generate_transaction_response(
        _state(
            TXN,
            **{
                "txn.results": [
                    {"date": "2026-07-01", "merchant": "스타벅스", "amount": 5000}
                ]
            },
        )
    )
    assert result["route_key"] == "success"
    assert "스타벅스" in result["final_response"]


def test_sum_transactions_spending_only():
    results = [
        {"type": "spending", "amount": 5000},
        {"type": "spending", "amount": 32000},
        {"type": "income", "amount": 2_500_000},
    ]
    result = sum_transactions(
        _state(SUM, **{"sum.results": results, "sum.txn_type": "spending"})
    )
    assert result["sum.total"] == 37000
    assert result["route_key"] == "done"


def test_generate_amount_summary_response_mentions_total():
    result = generate_amount_summary_response(
        _state(SUM, **{"sum.total": 49000, "sum.txn_type": "spending"})
    )
    assert result["route_key"] == "success"
    assert "49,000" in result["final_response"]
    assert "지출" in result["final_response"]
