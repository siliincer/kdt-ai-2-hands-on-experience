# redis의 연결 설정을 다룬다.
from typing import AsyncGenerator

import redis.asyncio as aioredis

from ..core.load_environment_var import settings

# 전역 커넥션 풀 선언 (애플리케이션 생명주기 동안 유지)
cache_pool = aioredis.ConnectionPool.from_url(
    str(settings.REDIS_CACHE_URL).strip(),
    max_connections=20,
    decode_responses=True,  # 문자열로 자동 디코딩 처리 활성화 (선택)
)

stream_pool = aioredis.ConnectionPool.from_url(
    str(settings.REDIS_STREAM_URL).strip(),
    max_connections=30,
    decode_responses=True,  # Stream 데이터 처리에 용이하도록 설정
)


# FastAPI 의존성 주입(DI) 함수 - Cache
async def get_redis_cache() -> AsyncGenerator[aioredis.Redis, None]:
    """일반 데이터 캐싱용 Redis 세션 주입"""
    client = aioredis.Redis(connection_pool=cache_pool)
    try:
        yield client
    finally:
        # 커넥션 풀을 사용하므로 close() 시 실제 소켓이 닫히지 않고 풀로 반환됩니다.
        await client.close()


# FastAPI 의존성 주입(DI) 함수 - Stream
async def get_redis_stream() -> AsyncGenerator[aioredis.Redis, None]:
    """이벤트/메시징 처리용 Redis Stream 세션 주입"""
    client = aioredis.Redis(connection_pool=stream_pool)
    try:
        yield client
    finally:
        await client.close()
