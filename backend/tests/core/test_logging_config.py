"""로깅 설정(dictConfig) 분기·필터 검증.

is_dev 에 따라 콘솔(DEBUG) / 파일 로테이션(INFO) 핸들러가 선택되는지, 기존 로거를
죽이지 않는지, request_id 필터가 레코드에 주입되는지 확인한다(파일 I/O 없이 config 딕셔너리
수준에서 검증).
"""

import logging

from backend.core import logging_config
from backend.core.logging_config import RequestIdFilter, build_logging_config
from backend.core.request_context import set_request_id


def test_dev_uses_console_debug(monkeypatch):
    monkeypatch.setattr(logging_config, "is_dev", True)
    cfg = build_logging_config()

    assert "console" in cfg["handlers"]
    assert "file" not in cfg["handlers"]
    assert cfg["handlers"]["console"]["class"] == "logging.StreamHandler"
    assert cfg["root"]["level"] == "DEBUG"
    assert cfg["root"]["handlers"] == ["console"]


def test_prod_uses_rotating_file_info(monkeypatch, tmp_path):
    monkeypatch.setattr(logging_config, "is_dev", False)
    monkeypatch.setattr(logging_config.settings, "LOG_LEVEL", "INFO")
    monkeypatch.setattr(logging_config.settings, "LOG_DIR", str(tmp_path))
    monkeypatch.setattr(logging_config.settings, "LOG_ROTATE_MAX_BYTES", 12345)
    monkeypatch.setattr(logging_config.settings, "LOG_BACKUP_COUNT", 3)

    cfg = build_logging_config()

    assert "file" in cfg["handlers"]
    assert "console" not in cfg["handlers"]
    file_h = cfg["handlers"]["file"]
    assert file_h["class"] == "logging.handlers.RotatingFileHandler"
    assert file_h["maxBytes"] == 12345
    assert file_h["backupCount"] == 3
    assert file_h["filename"].endswith("app.log")
    assert cfg["root"]["level"] == "INFO"
    # 로그 디렉터리가 생성된다.
    assert (tmp_path / "app.log").parent.exists()


def test_keeps_existing_loggers(monkeypatch):
    monkeypatch.setattr(logging_config, "is_dev", True)
    cfg = build_logging_config()
    # uvicorn.access·sqlalchemy 등 기존 로거를 비활성화하지 않는다.
    assert cfg["disable_existing_loggers"] is False


def test_request_id_filter_injects_value():
    f = RequestIdFilter()
    record = logging.LogRecord("n", logging.INFO, __file__, 1, "msg", None, None)

    set_request_id("req_abc123")
    assert f.filter(record) is True
    # request_id 는 필터가 LogRecord 에 동적으로 주입하는 속성이라 getattr 로 읽는다.
    assert getattr(record, "request_id") == "req_abc123"


def test_request_id_filter_defaults_to_dash():
    # ContextVar 가 비어 있으면(요청 스코프 밖) request_id 는 '-' 로 채운다.
    from backend.core import request_context

    request_context._request_id.set(None)
    f = RequestIdFilter()
    record = logging.LogRecord("n", logging.INFO, __file__, 1, "msg", None, None)
    assert f.filter(record) is True
    assert getattr(record, "request_id") == "-"
