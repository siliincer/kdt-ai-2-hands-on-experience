from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .base import engine

# 1. 비동기 세션 팩토리 설정
# 최신 비동기 세션에서는 autocommit=False 옵션이 기본값이며
# 명시하지 않는 것이 표준입니다.
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
    # 비동기 환경에서 커밋 후 객체 속성 접근 에러(InstanceState) 방지
)


# 2. FastAPI DB 세션 의존성 주입 함수
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    각 HTTP 요청마다 독립된 비동기 데이터베이스 세션을 생성하고 반환합니다.
    async with 컨텍스트 매니저가 예외 발생 시 자동 롤백 및 세션 종료(반환)를 보장합니다.
    """
    async with AsyncSessionLocal() as session:
        yield session
