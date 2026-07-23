"""애플리케이션 로깅 설정(중앙 집중).

로깅 정책
- 개발(is_dev=True): 콘솔(StreamHandler) + DEBUG.
- 운영(is_dev=False): 콘솔 끄고(sys.stdout 비용 회피) `backend_logs/app.log` 에 직접 기록 +
  크기 기반 회전(RotatingFileHandler, 기본 20MB × backupCount) + INFO.

Python 표준 logging(dictConfig)만 사용한다(structlog/otel/loki/json 은 차후 여지). uvicorn·
sqlalchemy 등 이미 설정된 로거를 죽이지 않도록 `disable_existing_loggers=False` 를 쓴다.
각 레코드에 요청 추적 id(X-Request-Id)를 주입해 로그 상관관계를 남긴다.
"""

from __future__ import annotations

import logging
import logging.config
from pathlib import Path

from ..utils.is_dev import is_dev
from .load_environment_var import settings
from .request_context import get_request_id

_LOG_FORMAT = "%(asctime)s %(levelname)-8s [%(name)s] [req=%(request_id)s] %(message)s"
_APP_LOG_FILENAME = "app.log"


class RequestIdFilter(logging.Filter):
    """현재 요청 스코프의 X-Request-Id 를 레코드에 주입한다(없으면 '-')."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True


def _log_dir() -> Path:
    path = Path(settings.LOG_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_logging_config() -> dict:
    """is_dev 에 따라 dictConfig 설정 딕셔너리를 만든다(테스트에서 직접 검증 가능)."""
    dev = is_dev
    level = "DEBUG" if dev else settings.LOG_LEVEL.strip().upper()

    handlers: dict[str, dict] = {}
    if dev:
        handlers["console"] = {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "filters": ["request_id"],
            "level": "DEBUG",
        }
    else:
        # 운영: 파일 로테이션만(콘솔 없음).
        log_path = _log_dir() / _APP_LOG_FILENAME
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "standard",
            "filters": ["request_id"],
            "level": level,
            "filename": str(log_path),
            "maxBytes": settings.LOG_ROTATE_MAX_BYTES,
            "backupCount": settings.LOG_BACKUP_COUNT,
            "encoding": "utf-8",
        }

    return {
        "version": 1,
        # uvicorn.access·sqlalchemy 등 기존 로거를 죽이지 않는다.
        "disable_existing_loggers": False,
        "filters": {
            "request_id": {"()": f"{__name__}.RequestIdFilter"},
        },
        "formatters": {
            "standard": {"format": _LOG_FORMAT},
        },
        "handlers": handlers,
        "root": {
            "level": level,
            "handlers": list(handlers.keys()),
        },
    }


def setup_logging() -> None:
    """앱 부팅 시 1회 호출. dictConfig 를 적용한다."""
    logging.config.dictConfig(build_logging_config())
