"""Workflow Slot 추출기가 공유하는 LLM 호출과 원문 검증 도구."""

from __future__ import annotations

import asyncio
import unicodedata
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel

_ModelT = TypeVar("_ModelT", bound=BaseModel)
_MODEL_TIMEOUT_SECONDS = 15.0


async def invoke_structured(
    schema: type[_ModelT],
    prompt: str,
    *,
    llm_factory: Callable[..., Any],
) -> _ModelT | None:
    """LLM Structured Output을 호출하고 장애나 검증 실패 시 None을 반환한다."""

    try:
        runnable = llm_factory(temperature=0.0).with_structured_output(schema)
        result = await asyncio.wait_for(
            runnable.ainvoke(prompt),
            timeout=_MODEL_TIMEOUT_SECONDS,
        )
        if isinstance(result, schema):
            return result
        return schema.model_validate(result)
    except Exception:
        return None


def grounded_phrase(value: str | None, message: str) -> str | None:
    """추출값이 사용자 원문에 실제로 존재할 때만 정규화 전 값을 반환한다."""

    if value is None:
        return None
    candidate = value.strip()
    if not candidate or len(candidate) > 100:
        return None
    return candidate if compact(candidate) in compact(message) else None


def compact(value: object) -> str:
    """원문 포함 여부 비교를 위해 유니코드와 공백을 정규화한다."""

    if not isinstance(value, str):
        return ""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(normalized.split())
