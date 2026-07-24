"""Agent 테스트 공통 fixture.

모든 테스트는 OPENAI_API_KEY 없이 결정적(deterministic) 폴백 경로로 실행한다.
로컬에 키가 설정돼 있어도 네트워크 호출이 발생하지 않도록 키를 제거하고
get_llm의 lru_cache를 비운다.
"""

from __future__ import annotations

import pytest

import agent.llm


@pytest.fixture(autouse=True)
def no_openai_key(monkeypatch):
    """LLM 경로를 강제로 실패시켜 키워드/규칙 폴백만 타게 한다.

    로컬 .env가 LLM_PROVIDER=vertex 등으로 설정돼 있어도 테스트가
    네트워크를 타지 않도록 provider도 기본값(openai)으로 되돌린다.
    """
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    agent.llm.get_llm.cache_clear()
    yield
    agent.llm.get_llm.cache_clear()
