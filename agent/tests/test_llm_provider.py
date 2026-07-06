"""LLM 제공자 전환(get_llm) 검증 — 네트워크 없이 분기만 확인한다."""

from __future__ import annotations

import pytest

from agent.llm import get_llm


@pytest.fixture(autouse=True)
def clear_llm_cache():
    get_llm.cache_clear()
    yield
    get_llm.cache_clear()


def test_default_provider_is_openai_and_requires_key(monkeypatch):
    """LLM_PROVIDER 미지정 = openai — 키 없으면 명확한 에러 (기존 동작 유지)."""
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        get_llm()


def test_openai_provider_builds_chat_openai(monkeypatch):
    from langchain_openai import ChatOpenAI

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("LLM_MODEL", raising=False)

    llm = get_llm()
    assert isinstance(llm, ChatOpenAI)
    assert llm.model_name == "gpt-4o-mini"  # 제공자 기본 모델


def test_vertex_provider_builds_chat_vertex(monkeypatch):
    """vertex 선택 시 ChatVertexAI가 project/location/모델과 함께 생성된다.

    실제 GCP 인증을 타지 않도록 클래스를 스텁으로 대체해 분기만 검증한다.
    """
    import langchain_google_vertexai

    captured: dict = {}

    class _StubVertex:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(langchain_google_vertexai, "ChatVertexAI", _StubVertex)
    monkeypatch.setenv("LLM_PROVIDER", "vertex")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-project")
    monkeypatch.setenv("VERTEX_LOCATION", "asia-northeast3")
    monkeypatch.delenv("LLM_MODEL", raising=False)

    llm = get_llm()
    assert isinstance(llm, _StubVertex)
    assert captured["model"] == "gemini-2.5-flash"  # vertex 기본 모델
    assert captured["project"] == "my-project"
    assert captured["location"] == "asia-northeast3"
    assert captured["temperature"] == 0.0


def test_provider_model_mismatch_falls_back_to_default(monkeypatch):
    """예전 .env의 gpt 모델명이 vertex를 조용히 깨뜨리지 않는다 (가드)."""
    import langchain_google_vertexai

    captured: dict = {}

    class _StubVertex:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(langchain_google_vertexai, "ChatVertexAI", _StubVertex)
    monkeypatch.setenv("LLM_PROVIDER", "vertex")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")  # openai용 모델이 남은 상황

    get_llm()
    assert captured["model"] == "gemini-2.5-flash"  # vertex 기본으로 복원


def test_llm_model_env_overrides_default(monkeypatch):
    import langchain_google_vertexai

    captured: dict = {}

    class _StubVertex:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(langchain_google_vertexai, "ChatVertexAI", _StubVertex)
    monkeypatch.setenv("LLM_PROVIDER", "vertex")
    monkeypatch.setenv("LLM_MODEL", "gemini-2.5-pro")

    get_llm()
    assert captured["model"] == "gemini-2.5-pro"
