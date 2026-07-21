# postgresql의 연결 설정을 다룬다.
from typing import AsyncGenerator

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from ..core.load_environment_var import settings
from ..utils.is_dev import is_dev

# [보강] asyncpg 드라이버 명시 강제화 (postgresql:// -> postgresql+asyncpg://)
raw_url = str(settings.DATABASE_URL).strip()
if raw_url.startswith("postgresql://"):
    raw_url = raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)

SQLALCHEMY_DATABASE_URL = make_url(raw_url)

# 1. 비동기 엔진 설정
engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={
        "command_timeout": 30,
    },
    pool_size=20,  # 기본 풀 커넥션 크기
    max_overflow=10,  # 최대 초과 허용 커넥션 개수
    pool_timeout=30,  # 커넥션 획득 대기시간 (초)
    pool_recycle=1800,  # 연결 재사용 주기 (30분)
    pool_pre_ping=True,  # 연결 유효성 검사 활성화 (SELECT 1 실행)
    echo=is_dev,  # 개발 서버/디버깅 모드일 때 실행된 SQL 쿼리 출력
)


# 2. SQLAlchemy 2.0 표준 Base 모델 선언
class Base(AsyncAttrs, DeclarativeBase):
    """
    모든 테이블 모델의 부모가 되는 추상 베이스 클래스입니다.
    AsyncAttrs를 함께 상속받아 비동기 관계(relationship)
    지연 로딩 시 안전하게 동작합니다.
    """

    pass


# 3. 비동기 세션 팩토리 설정
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
    # 비동기 환경에서 커밋 후 객체 속성 접근 에러(InstanceState) 방지
)


# 4. FastAPI 의존성 주입(DI) 함수
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    HTTP 요청마다 비동기 DB 세션을 주입합니다.

    커밋은 repository 계층 책임(함수별 commit 컨벤션)이고, 여기서는 예외 경로만
    방어한다: 네트워크 단절·DB 다운·비즈니스 예외 등 어떤 실패든 부분 flush 잔재가
    남지 않도록 명시 rollback 후 프레임워크로 재전파한다(500 등 응답은 핸들러 몫).
    컨텍스트 매니저(async with)가 세션 close(풀 반환)를 항상 보장한다.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
