"""Slot 추출 공통 LLM 호출과 원문 검증 도구 테스트."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from agent.workflows.slot_extraction_support import grounded_phrase, invoke_structured


class _Slots(BaseModel):
    account_hint: str | None = None


class _StructuredLlm:
    def __init__(self, result: Any) -> None:
        self._result = result

    def with_structured_output(self, schema: type[BaseModel]) -> _StructuredLlm:
        del schema
        return self

    async def ainvoke(self, prompt: str) -> Any:
        del prompt
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


@pytest.mark.asyncio
async def test_invoke_structured_validates_mapping_result() -> None:
    result = await invoke_structured(
        _Slots,
        "계좌 힌트를 추출해라.",
        llm_factory=lambda **_: _StructuredLlm({"account_hint": "주거래"}),
    )

    assert result == _Slots(account_hint="주거래")


@pytest.mark.asyncio
async def test_invoke_structured_returns_none_on_llm_failure() -> None:
    result = await invoke_structured(
        _Slots,
        "계좌 힌트를 추출해라.",
        llm_factory=lambda **_: _StructuredLlm(RuntimeError("LLM unavailable")),
    )

    assert result is None


def test_grounded_phrase_normalizes_case_width_and_whitespace() -> None:
    assert grounded_phrase("ＡＢＣ 카드", "abc카드 결제 내역") == "ＡＢＣ 카드"
    assert grounded_phrase("신한은행", "시난 통장 잔액") is None
