"""LLM 클라이언트.

OpenAI 기반 LLM을 한 곳에서 만들어 재사용한다.
- .env의 OPENAI_API_KEY / LLM_MODEL을 읽는다.
- 구조화 출력(structured output)이 필요하면 with_structured_output(스키마)로 쓴다.
- 온도(temperature)는 기본 0.0 — 금융 도메인이라 재현성/일관성을 우선한다.
"""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

_DEFAULT_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")


@lru_cache(maxsize=4)
def get_llm(temperature: float = 0.0, model: str | None = None) -> ChatOpenAI:
    """설정된 모델의 ChatOpenAI 인스턴스를 반환한다(같은 설정은 캐시 재사용).

    OPENAI_API_KEY가 없으면 첫 호출 시 명확한 에러를 던진다.
    """
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY가 설정되지 않았습니다. "
            ".env.example을 .env로 복사하고 키를 입력하세요."
        )
    return ChatOpenAI(model=model or _DEFAULT_MODEL, temperature=temperature)
