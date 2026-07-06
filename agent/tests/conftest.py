"""Agent 테스트 공통 fixture.

모든 테스트는 OPENAI_API_KEY 없이 결정적(deterministic) 폴백 경로로 실행한다.
로컬에 키가 설정돼 있어도 네트워크 호출이 발생하지 않도록 키를 제거하고
get_llm의 lru_cache를 비운다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import agent.llm


@pytest.fixture(autouse=True)
def no_openai_key(monkeypatch):
    """LLM 경로를 강제로 실패시켜 키워드/규칙 폴백만 타게 한다."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    agent.llm.get_llm.cache_clear()
    yield
    agent.llm.get_llm.cache_clear()


@pytest.fixture()
def client() -> TestClient:
    from agent.main import app

    return TestClient(app)
