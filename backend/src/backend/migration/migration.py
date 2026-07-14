from pathlib import Path

from alembic import command
from alembic.config import Config

# backend/alembic.ini 절대경로. cwd 에 의존하지 않도록 __file__ 기준으로 잡는다
# (repo 루트/서비스 디렉토리 어디서 실행해도 동일). alembic.ini 의 script_location
# 은 %(here)s(ini 파일 디렉토리) 기준이라 이 경로만으로 migrations/ 도 해결된다.
_ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"


def run_migrations():
    alembic_cfg = Config(str(_ALEMBIC_INI))
    command.upgrade(alembic_cfg, "head")
