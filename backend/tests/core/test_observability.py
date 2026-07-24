"""분산추적 설정(core/observability) 단위 테스트.

핵심 계약은 "기본 꺼짐이면 완전 no-op" 이다. 실제 계측을 켜면 전역 TracerProvider 가
바뀌어 다른 테스트에 영향을 주므로, 여기서는 게이트 off 경로와 순수 헬퍼만 검증한다.
"""

from fastapi import FastAPI

from backend.core import observability


def test_setup_tracing_is_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(observability.settings, "OTEL_ENABLED", False)
    app = FastAPI()

    assert observability.setup_tracing(app) is False


def test_setup_tracing_skips_when_packages_missing(monkeypatch):
    # OTEL_ENABLED=true 라도 opentelemetry 미설치면 앱을 깨지 않고 건너뛴다.
    monkeypatch.setattr(observability.settings, "OTEL_ENABLED", True)

    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("opentelemetry"):
            raise ImportError("simulated missing package")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    assert observability.setup_tracing(FastAPI()) is False


def test_get_trace_id_is_none_without_active_span():
    # 요청 스코프 밖(활성 스팬 없음)에서는 None → 로그 필터가 '-' 로 채운다.
    assert observability.get_trace_id() is None


def test_excluded_urls_cover_noisy_and_streaming_paths():
    # 폴링(health/metrics)과 장수명 SSE 스트림은 스팬을 만들지 않는다.
    for path in ("health", "metrics", "api/v1/sse/connect"):
        assert path in observability._EXCLUDED_URLS
