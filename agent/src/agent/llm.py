"""LLM 클라이언트.

LLM 인스턴스를 한 곳에서 만들어 재사용한다. 제공자는 환경변수로 선택한다:

  LLM_PROVIDER=openai (기본): OPENAI_API_KEY 필요
  LLM_PROVIDER=vertex:        Google Cloud Vertex AI (Gemini).
                              ADC 인증(gcloud auth application-default login)
                              또는 GOOGLE_APPLICATION_CREDENTIALS(서비스 계정
                              JSON 경로) 필요. GOOGLE_CLOUD_PROJECT로 프로젝트,
                              VERTEX_LOCATION으로 리전 지정(기본 us-central1).
  LLM_PROVIDER=ollama:        로컬/사내 Ollama 서버를 사용한다.
                              OLLAMA_BASE_URL, OLLAMA_MODEL로 접속 대상과
                              모델을 지정한다.

공통:
  - LLM_MODEL로 모델 지정 (미지정 시 제공자별 기본값)
  - 구조화 출력이 필요하면 with_structured_output(스키마)로 쓴다
  - 온도(temperature)는 기본 0.0 — 금융 도메인이라 재현성/일관성 우선
  - 생성/호출 실패는 호출부(tool/matcher)가 잡아 규칙 기반으로 폴백한다
"""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI


def _load_local_environment() -> None:
    if os.getenv("AGENT_DISABLE_DOTENV") != "1":
        load_dotenv()


_load_local_environment()

# 제공자별 기본 모델 (LLM_MODEL 미지정 시)
_DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "vertex": "gemini-2.5-flash",
    "ollama": "qwen2.5:3b",
}


def _provider() -> str:
    return os.getenv("LLM_PROVIDER", "openai").strip().lower()


def _resolve_model(provider: str, model: str | None) -> str:
    if provider == "ollama":
        resolved_model = (
            model
            or os.getenv("OLLAMA_MODEL")
            or os.getenv("LLM_MODEL")
            or _DEFAULT_MODELS["ollama"]
        )
    else:
        resolved_model = (
            model
            or os.getenv("LLM_MODEL")
            or _DEFAULT_MODELS.get(provider, _DEFAULT_MODELS["openai"])
        )

    return resolved_model


@lru_cache(maxsize=4)
def get_llm(temperature: float = 0.0, model: str | None = None) -> BaseChatModel:
    """LLM_PROVIDER에 맞는 챗 모델 인스턴스를 반환한다 (같은 설정은 캐시).

    환경변수를 바꿨다면 get_llm.cache_clear()를 호출해야 반영된다.
    """
    provider = _provider()
    if provider not in _DEFAULT_MODELS:
        supported = ", ".join(sorted(_DEFAULT_MODELS))
        raise RuntimeError(
            f"지원하지 않는 LLM_PROVIDER입니다: {provider}. 지원 값: {supported}"
        )

    resolved_model = _resolve_model(provider, model)

    if provider == "vertex":
        # vertex 미사용 환경에서 import 비용/의존 문제를 피하려고 지연 import
        from langchain_google_vertexai import ChatVertexAI

        return ChatVertexAI(
            model=resolved_model,
            temperature=temperature,
            project=os.getenv("GOOGLE_CLOUD_PROJECT") or None,
            location=os.getenv("VERTEX_LOCATION", "us-central1"),
        )

    if provider == "ollama":
        # Ollama 미사용 환경에서 import 비용/의존 문제를 피하려고 지연 import
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=resolved_model,
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            temperature=temperature,
            client_kwargs={"trust_env": False},
            async_client_kwargs={"trust_env": False},
        )

    # 기본: openai (LLM_PROVIDER 미지정 포함 — 기존 동작 유지)
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY가 설정되지 않았습니다. "
            ".env.example을 .env로 복사하고 키를 입력하거나, "
            "LLM_PROVIDER=vertex 또는 LLM_PROVIDER=ollama를 사용하세요."
        )
    return ChatOpenAI(model=resolved_model, temperature=temperature)
