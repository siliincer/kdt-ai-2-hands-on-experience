"""기본 출금 계좌·계좌 별칭 변경 공통 LLM 우선 Slot 추출 테스트."""

from __future__ import annotations

from typing import Any

import pytest

from agent.workflows import setting_slot_extraction


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
async def test_default_account_llm_fills_account_hint(monkeypatch) -> None:
    message = "이번 달부터 급여 통장을 주로 쓸 계좌로 바꾸고 싶어"
    fake = _FakeStructuredLlm({"account_hint": "급여 통장"})
    monkeypatch.setattr(setting_slot_extraction, "get_llm", lambda **_: fake)

    result = await setting_slot_extraction.extract_default_account_slots_llm_first(message)

    assert result == {"account_hint": "급여 통장"}
    assert "오타 교정" in fake.prompts[0]


@pytest.mark.asyncio
async def test_default_account_ungrounded_correction_is_rejected(monkeypatch) -> None:
    message = "신후은행 계좌를 기본계좌로 바꿔줘"
    fake = _FakeStructuredLlm({"account_hint": "신한은행 계좌"})
    monkeypatch.setattr(setting_slot_extraction, "get_llm", lambda **_: fake)

    result = await setting_slot_extraction.extract_default_account_slots_llm_first(message)

    assert result == {"account_hint": "신후은행 계좌"}


@pytest.mark.asyncio
async def test_default_account_llm_failure_uses_rule_fallback(monkeypatch) -> None:
    message = "급여 통장을 기본계좌로 바꿔줘"
    failed = _FailedStructuredLlm()
    monkeypatch.setattr(setting_slot_extraction, "get_llm", lambda **_: failed)

    result = await setting_slot_extraction.extract_default_account_slots_llm_first(message)

    assert result == setting_slot_extraction.extract_default_account_slots_by_rule(message)


@pytest.mark.asyncio
async def test_account_alias_llm_fills_alias_rule_misses(monkeypatch) -> None:
    message = "저축 계좌 이름을 커피값으로 하고 싶어"
    fake = _FakeStructuredLlm({"account_hint": "저축 계좌", "alias": "커피값"})
    monkeypatch.setattr(setting_slot_extraction, "get_llm", lambda **_: fake)

    result = await setting_slot_extraction.extract_account_alias_slots_llm_first(message)

    assert result == {"account_hint": "저축 계좌", "alias": "커피값"}


@pytest.mark.asyncio
async def test_account_alias_ungrounded_correction_is_rejected(monkeypatch) -> None:
    """AGENTS.md의 자연어 Slot 추출 규칙이 명시적으로 우려하는 케이스.

    LLM이 사용자 원문 별칭("여행자금")을 동의어("여행경비")로 "교정"해서
    반환해도, 사용자 원문에 없는 표현이므로 grounding이 거부하고 원문 그대로
    유지해야 한다.
    """

    message = "생활비 통장 별칭을 여행자금으로 바꿔줘"
    fake = _FakeStructuredLlm({"account_hint": "생활비 통장", "alias": "여행경비"})
    monkeypatch.setattr(setting_slot_extraction, "get_llm", lambda **_: fake)

    result = await setting_slot_extraction.extract_account_alias_slots_llm_first(message)

    assert result == {"account_hint": "생활비 통장", "alias": "여행자금"}


@pytest.mark.asyncio
async def test_account_alias_llm_failure_uses_rule_fallback(monkeypatch) -> None:
    message = "생활비 통장 별칭을 '여행 자금'으로 바꿔줘"
    failed = _FailedStructuredLlm()
    monkeypatch.setattr(setting_slot_extraction, "get_llm", lambda **_: failed)

    result = await setting_slot_extraction.extract_account_alias_slots_llm_first(message)

    assert result == setting_slot_extraction.extract_account_alias_slots_by_rule(message)
