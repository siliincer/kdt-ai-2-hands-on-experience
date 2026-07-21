"""조회 Workflow 공통 LLM 우선 Slot 추출 테스트."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from agent.workflows import query_slot_extraction


class _FakeStructuredLlm:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self._schema: type[Any] | None = None
        self.prompts: list[str] = []

    def with_structured_output(self, schema: type[Any]) -> _FakeStructuredLlm:
        self._schema = schema
        return self

    async def ainvoke(self, prompt: str) -> Any:
        self.prompts.append(prompt)
        if self._schema is None:
            raise AssertionError("구조화 출력 Schema가 설정되지 않았습니다.")
        return self._schema.model_validate(self._payload)


class _FailedStructuredLlm:
    def with_structured_output(self, schema: type[Any]) -> _FailedStructuredLlm:
        return self

    async def ainvoke(self, prompt: str) -> Any:
        raise RuntimeError("LLM unavailable")


@pytest.mark.asyncio
async def test_account_hint_uses_llm_before_rule_fallback(monkeypatch) -> None:
    fake = _FakeStructuredLlm({"account_hint": "주거래"})
    monkeypatch.setattr(query_slot_extraction, "get_llm", lambda **_: fake)

    result = await query_slot_extraction.extract_account_list_slots_llm_first(
        "주거래로 쓰는 것만 보여줘"
    )

    assert result == {"account_hint": "주거래"}
    assert "오타 교정" in fake.prompts[0]


@pytest.mark.asyncio
async def test_ungrounded_llm_account_expansion_is_rejected(monkeypatch) -> None:
    fake = _FakeStructuredLlm(
        {
            "account_hint": "신한은행",
            "all_accounts_requested": False,
        }
    )
    monkeypatch.setattr(query_slot_extraction, "get_llm", lambda **_: fake)

    result = await query_slot_extraction.extract_balance_slots_llm_first(
        "시난 통장 잔액 알려줘"
    )

    assert result == {
        "account_hint": "시난 통장",
        "all_accounts_requested": False,
    }


@pytest.mark.asyncio
async def test_ungrounded_merchant_expansion_is_rejected(monkeypatch) -> None:
    fake = _FakeStructuredLlm(
        {
            "account_hint": None,
            "period_preset": "this_month",
            "start_date": None,
            "end_date": None,
            "keyword": "배달의민족",
            "summary_type": "spending",
        }
    )
    monkeypatch.setattr(query_slot_extraction, "get_llm", lambda **_: fake)

    result = await query_slot_extraction.extract_amount_summary_slots_llm_first(
        "이번 달 배민에서 얼마 썼어?",
        date(2026, 7, 19),
    )

    assert result["keyword"] == "배민"


@pytest.mark.asyncio
async def test_transaction_llm_normalizes_period_semantics_deterministically(
    monkeypatch,
) -> None:
    fake = _FakeStructuredLlm(
        {
            "account_hint": None,
            "all_accounts_requested": False,
            "period_preset": "last_month",
            "start_date": None,
            "end_date": None,
            "keyword": "카페",
            "transaction_type": "card_payment",
        }
    )
    monkeypatch.setattr(query_slot_extraction, "get_llm", lambda **_: fake)

    result = await query_slot_extraction.extract_transaction_slots_llm_first(
        "전월 카페 결제들을 보여줘",
        date(2026, 7, 19),
    )

    assert result == {
        "account_hint": None,
        "all_accounts_requested": False,
        "start_date": "2026-06-01",
        "end_date": "2026-06-30",
        "keyword": "카페",
        "transaction_type": "card_payment",
    }


@pytest.mark.asyncio
async def test_llm_failure_uses_deterministic_summary_fallback(monkeypatch) -> None:
    failed = _FailedStructuredLlm()
    monkeypatch.setattr(query_slot_extraction, "get_llm", lambda **_: failed)

    result = await query_slot_extraction.extract_amount_summary_slots_llm_first(
        "이번 달 나 배민에서 얼마 썼어?",
        date(2026, 7, 19),
    )

    assert result == {
        "account_hint": None,
        "all_accounts_requested": True,
        "start_date": "2026-07-01",
        "end_date": "2026-07-19",
        "summary_type": "spending",
        "keyword": "배민",
    }
