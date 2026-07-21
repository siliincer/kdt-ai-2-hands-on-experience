"""본인이체·타인송금 공통 LLM 우선 Slot 추출 테스트."""

from __future__ import annotations

from typing import Any

import pytest

from agent.workflows import transfer_slot_extraction


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
async def test_internal_transfer_llm_fills_hint_rule_misses(monkeypatch) -> None:
    message = "생활비 통장에서 비상금으로 10만 원 보내줘"
    fake = _FakeStructuredLlm(
        {
            "from_account_hint": "생활비 통장",
            "to_account_hint": "비상금",
            "amount": 100_000,
        }
    )
    monkeypatch.setattr(transfer_slot_extraction, "get_llm", lambda **_: fake)

    result = await transfer_slot_extraction.extract_internal_transfer_slots_llm_first(message)

    assert result == {
        "from_account_hint": "생활비 통장",
        "to_account_hint": "비상금",
        "amount": 100_000,
    }
    assert "오타 교정" in fake.prompts[0]


@pytest.mark.asyncio
async def test_internal_transfer_ungrounded_account_correction_is_rejected(
    monkeypatch,
) -> None:
    message = "신후은행에서 10만원 보내줘"
    fake = _FakeStructuredLlm(
        {
            "from_account_hint": "신한은행",
            "to_account_hint": None,
            "amount": 100_000,
        }
    )
    monkeypatch.setattr(transfer_slot_extraction, "get_llm", lambda **_: fake)

    result = await transfer_slot_extraction.extract_internal_transfer_slots_llm_first(message)

    assert result == {
        "from_account_hint": "신후은행",
        "to_account_hint": None,
        "amount": 100_000,
    }


@pytest.mark.asyncio
async def test_internal_transfer_llm_failure_uses_rule_fallback(monkeypatch) -> None:
    message = "주거래 계좌에서 저축 계좌로 5만원 이체해줘"
    failed = _FailedStructuredLlm()
    monkeypatch.setattr(transfer_slot_extraction, "get_llm", lambda **_: failed)

    result = await transfer_slot_extraction.extract_internal_transfer_slots_llm_first(message)

    assert result == transfer_slot_extraction.extract_internal_transfer_slots_by_rule(message)


@pytest.mark.asyncio
async def test_external_transfer_llm_fills_recipient_hint_rule_misses(
    monkeypatch,
) -> None:
    message = "민지 앞으로 5만원 보내줘"
    fake = _FakeStructuredLlm(
        {
            "recipient_name_hint": "민지",
            "from_account_hint": None,
            "amount": 50_000,
        }
    )
    monkeypatch.setattr(transfer_slot_extraction, "get_llm", lambda **_: fake)

    result = await transfer_slot_extraction.extract_external_transfer_slots_llm_first(message)

    assert result == {
        "recipient_name_hint": "민지",
        "from_account_hint": None,
        "amount": 50_000,
    }


@pytest.mark.asyncio
async def test_external_transfer_ungrounded_recipient_correction_is_rejected(
    monkeypatch,
) -> None:
    """AGENTS.md의 자연어 Slot 추출 규칙이 명시적으로 우려하는 케이스.

    LLM이 오타 수취인 이름("철숴")을 정상 이름("철수")으로 "교정"해서 반환해도,
    사용자 원문에 없는 표현이므로 grounding이 거부하고 원문 그대로 유지해야 한다.
    """

    message = "철숴한테 5만원 보내줘"
    fake = _FakeStructuredLlm(
        {
            "recipient_name_hint": "철수",
            "from_account_hint": None,
            "amount": 50_000,
        }
    )
    monkeypatch.setattr(transfer_slot_extraction, "get_llm", lambda **_: fake)

    result = await transfer_slot_extraction.extract_external_transfer_slots_llm_first(message)

    assert result == {
        "recipient_name_hint": "철숴",
        "from_account_hint": None,
        "amount": 50_000,
    }


@pytest.mark.asyncio
async def test_external_transfer_llm_failure_uses_rule_fallback(monkeypatch) -> None:
    message = "국민은행 계좌에서 철수에게 5만원 보내줘"
    failed = _FailedStructuredLlm()
    monkeypatch.setattr(transfer_slot_extraction, "get_llm", lambda **_: failed)

    result = await transfer_slot_extraction.extract_external_transfer_slots_llm_first(message)

    assert result == transfer_slot_extraction.extract_external_transfer_slots_by_rule(message)
