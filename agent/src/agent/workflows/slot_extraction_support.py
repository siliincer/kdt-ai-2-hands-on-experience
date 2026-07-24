"""Workflow Slot 추출기가 공유하는 LLM 호출과 원문 검증 도구."""

from __future__ import annotations

import asyncio
import unicodedata
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel

_ModelT = TypeVar("_ModelT", bound=BaseModel)
_MODEL_TIMEOUT_SECONDS = 15.0

# 특정 계좌를 지칭하지 않는 일반어(compact 형태). 이런 힌트로 Backend를 필터하면
# bank_name·alias·account_type 어디에도 안 걸려 보유 계좌가 0건으로 보이므로,
# 힌트 없음(전체 조회)으로 정규화한다.
GENERIC_ACCOUNT_HINTS: frozenset[str] = frozenset(
    {
        "계좌",
        "통장",
        "목록",
        "계좌목록",
        "통장목록",
        "내계좌",
        "내통장",
        "내계좌목록",
        "전체계좌",
        "전체통장",
        "전체계좌목록",
        "모든계좌",
        "모든통장",
        "모든계좌목록",
        "전계좌",
    }
)


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


def scrub_generic_account_hint(value: str | None) -> str | None:
    """힌트 전체가 일반어일 때만 None으로 바꾼다.

    compact 전체 일치로만 판정하므로 "생활비 계좌"처럼 일반어를 포함하는
    구체적 힌트는 그대로 보존된다.
    """

    if value is None:
        return None
    return None if compact(value) in GENERIC_ACCOUNT_HINTS else value


def compact(value: object) -> str:
    """원문 포함 여부 비교를 위해 유니코드와 공백을 정규화한다."""

    if not isinstance(value, str):
        return ""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(normalized.split())
