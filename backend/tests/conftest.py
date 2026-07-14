#  테스트 전반에 공유되는 설정과 Fixture(준비물)를 넣는 곳

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app as fastapi_app  # 실제 FastAPI 인스턴스 위치


@pytest.fixture
def app():
    return fastapi_app


# 1. 테스트용 클라이언트 Fixture
# def test_read_root(client): 로 바로 주입 가능
@pytest.fixture
def client():
    """FastAPI 테스트 클라이언트를 반환합니다.

    lifespan 의 run_migrations() 는 실제 postgres 에 연결(alembic upgrade)하므로,
    DB 없는 CI(GitHub Actions)에서 fixture setup 이 깨진다. client fixture 를
    쓰는 테스트는 인증(401) 검증만 하고 DB 를 건드리지 않으므로 마이그레이션을
    mock 처리한다(스키마 불필요). 실제 마이그레이션은 앱 부팅 시에만 수행된다.
    """
    with patch("backend.main.run_migrations"):
        with TestClient(fastapi_app) as c:
            yield c


# lifespan 트리거 후 백그라운드 태스크나 커넥션 풀이
# 메모리에 계속 남아있게 됩니다.
# 따라서, 테스트가 끝나면 with 블록이 정상적으로 닫히도록 제어하기 위해
# 반드시 yield를 사용해야 합니다


# 2. 테스트 환경 변수 설정 (필요 시)
@pytest.fixture(scope="session", autouse=True)
def setup_test_env():
    """테스트 시작 전 환경 변수 등을 세팅합니다."""
    import os

    os.environ["DATABASE_URL"] = "sqlite:///:memory:"  # 예시
    yield
