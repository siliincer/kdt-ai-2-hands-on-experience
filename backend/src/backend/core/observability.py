"""OpenTelemetry 분산추적 설정 (트레이스 → OTLP → Grafana Tempo).

설계 원칙:
- **기본 꺼짐**: `OTEL_ENABLED=false` 면 아무것도 하지 않는다(완전 no-op). 테스트/CI/운영 무영향,
  롤백은 환경변수 한 줄.
- **자동 계측만 사용**: FastAPI/HTTPX/SQLAlchemy/Redis/asyncpg 계측기가 스팬을 만들므로
  비즈니스 코드는 건드리지 않는다.
- **선택 의존성**: OTel 패키지는 `[project.optional-dependencies] otel` 이라 미설치일 수 있다.
  import 실패는 경고 로그만 남기고 앱을 계속 띄운다(관측이 서비스를 깨지 않는다).

민감정보: 스팬에 계좌번호 원문·비밀번호·토큰을 넣지 않는다. HTTP 계측기는 기본적으로 바디를
수집하지 않으며, 민감 헤더도 캡처하지 않도록 별도 설정을 켜지 않는다.
"""

import logging

from fastapi import FastAPI

from ..utils.is_dev import is_dev
from .load_environment_var import settings

logger = logging.getLogger(__name__)

# 스팬을 만들지 않을 경로.
# - /health, /metrics: 폴링 노이즈
# - /api/v1/sse/connect: 장수명 스트리밍이라 스팬이 비정상적으로 커진다
_EXCLUDED_URLS = "health,metrics,api/v1/sse/connect"


def setup_tracing(app: FastAPI) -> bool:
    """FastAPI 앱에 트레이싱을 붙인다. 활성화되면 True.

    부팅 1회만 호출한다(`main.py`). 실패해도 예외를 밖으로 던지지 않는다.
    """
    if not settings.OTEL_ENABLED:
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import ALWAYS_ON, ParentBasedTraceIdRatio
    except ImportError:
        logger.warning("OTEL_ENABLED=true 이지만 opentelemetry 패키지가 없어 트레이싱을 건너뜁니다.")
        return False

    resource = Resource.create(
        {
            "service.name": settings.OTEL_SERVICE_NAME,
            "deployment.environment": settings.APP_ENV,
        }
    )
    sampler = ALWAYS_ON if is_dev else ParentBasedTraceIdRatio(settings.OTEL_SAMPLE_RATIO)
    provider = TracerProvider(resource=resource, sampler=sampler)
    # Batch: 백그라운드에서 비동기 전송 → 요청 지연에 영향을 주지 않는다.
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT, insecure=True))
    )
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app, excluded_urls=_EXCLUDED_URLS)
    # BE→Agent, BE→계정계 호출. traceparent 헤더를 자동 주입해 하위 서비스와 이어붙일 수 있게 한다.
    HTTPXClientInstrumentor().instrument()
    RedisInstrumentor().instrument()
    _instrument_sqlalchemy()

    logger.info(
        "OpenTelemetry 트레이싱 활성화: service=%s endpoint=%s",
        settings.OTEL_SERVICE_NAME,
        settings.OTEL_EXPORTER_OTLP_ENDPOINT,
    )
    return True


def _instrument_sqlalchemy() -> None:
    """비동기 엔진의 sync 엔진에 SQLAlchemy 계측을 붙인다(쿼리 스팬)."""
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        from ..db.postgres import engine

        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
    except Exception:  # noqa: BLE001 - 관측 실패가 서비스를 깨지 않는다
        logger.warning("SQLAlchemy 계측을 건너뜁니다.", exc_info=True)


def get_trace_id() -> str | None:
    """현재 스팬의 trace_id(32자리 hex). 스팬이 없거나 OTel 미설치면 None.

    로그 포맷에 trace_id 를 함께 남겨 로그 → Tempo 트레이스로 점프할 수 있게 한다.
    """
    try:
        from opentelemetry import trace
    except ImportError:
        return None

    span = trace.get_current_span()
    context = span.get_span_context()
    if not context.is_valid:
        return None
    return format(context.trace_id, "032x")
