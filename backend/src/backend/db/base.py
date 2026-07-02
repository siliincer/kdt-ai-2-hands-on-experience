from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncAttrs, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from ..core.load_environment_var import settings  # 환경변수 로드
from ..utils.is_dev import is_dev

# 1. DB 연결 설정 (PostgreSQL + asyncpg 기준)
SQLALCHEMY_DATABASE_URL = make_url(str(settings.DATABASE_URL).strip())

# PostgreSQL 호환 및 비동기 드라이버 최적화 설정
engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={
        # asyncpg의 기본 인코딩은 항상 utf8이므로
        # 별도 지정 없이 이모지가 정상 작동합니다.
        "command_timeout": 30,  # 쿼리 실행 제한 시간 (초 단위 타임아웃 설정)
    },
    pool_size=20,  # 기본 풀 커넥션 크기
    max_overflow=10,  # 최대 초과 허용 커넥션 개수
    pool_timeout=30,  # 커넥션 획득 대기시간 (초)
    pool_recycle=1800,  # 연결 재사용 주기 (30분)
    pool_pre_ping=True,  # 연결 유효성 검사 활성화 (SELECT 1 실행)
    echo=is_dev,  # 개발 서버/디버깅 모드일 때 실행된 SQL 쿼리 출력
)


# 2. SQLAlchemy 2.0 표준 Base 모델 클래스 정의
class Base(AsyncAttrs, DeclarativeBase):
    """
    모든 테이블 모델의 부모가 되는 추상 베이스 클래스입니다.
    AsyncAttrs를 함께 상속받아 비동기 관계(relationship)
    지연 로딩 시 안전하게 동작합니다.
    """

    pass
