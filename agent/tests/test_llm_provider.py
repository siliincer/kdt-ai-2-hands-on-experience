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


def test_ollama_provider_builds_chat_ollama(monkeypatch):
    """ollama 선택 시 OpenAI 키 없이 로컬 Ollama 설정으로 생성된다."""
    import langchain_ollama

    captured: dict = {}

    class _StubOllama:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(langchain_ollama, "ChatOllama", _StubOllama)
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.2:3b")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)

    llm = get_llm()
    assert isinstance(llm, _StubOllama)
    assert captured["model"] == "llama3.2:3b"
    assert captured["base_url"] == "http://host.docker.internal:11434"
    assert captured["temperature"] == 0.0


def test_ollama_explicit_model_overrides_env(monkeypatch):
    import langchain_ollama

    captured: dict = {}

    class _StubOllama:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(langchain_ollama, "ChatOllama", _StubOllama)
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:3b")

    get_llm(model="llama3.2:3b")
    assert captured["model"] == "llama3.2:3b"


def test_ollama_provider_uses_default_model(monkeypatch):
    import langchain_ollama

    captured: dict = {}

    class _StubOllama:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(langchain_ollama, "ChatOllama", _StubOllama)
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)

    get_llm()
    assert captured["model"] == "qwen2.5:3b"
    assert captured["base_url"] == "http://localhost:11434"


def test_ollama_model_mismatch_falls_back_to_default(monkeypatch):
    import langchain_ollama

    captured: dict = {}

    class _StubOllama:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(langchain_ollama, "ChatOllama", _StubOllama)
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")  # openai용 모델이 남은 상황
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)

    get_llm()
    assert captured["model"] == "qwen2.5:3b"


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


def test_unknown_provider_raises_clear_error(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")

    with pytest.raises(RuntimeError, match="지원하지 않는 LLM_PROVIDER"):
        get_llm()
