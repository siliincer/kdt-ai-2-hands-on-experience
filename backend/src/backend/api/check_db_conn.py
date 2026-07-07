import asyncpg
import redis.asyncio as aioredis
from fastapi import APIRouter

from ..core.load_environment_var import settings
from ..schemas.response import CommonResponse
from ..utils.build_response import success_response

health_router = APIRouter(prefix="/dbhealth", tags=["Health"])


@health_router.get("", response_model=CommonResponse[dict])
async def check_health():
    status = {}

    # 1. PostgreSQL (asyncpg) 연결 확인
    try:
        # asyncpg.connect는 비동기 함수이므로 await가 필수입니다.
        conn = await asyncpg.connect(settings.DATABASE_URL, timeout=3)
        await conn.close()
        status["postgres"] = "connected"
    except Exception as e:
        status["postgres"] = f"failed: {str(e)}"

    # 2. Redis Cache 연결 확인
    try:
        r_cache = aioredis.from_url(str(settings.REDIS_CACHE_URL), socket_timeout=3)
        await r_cache.ping()
        await r_cache.close()  # 연결 풀 자원 반환
        status["redis_cache"] = "connected"
    except Exception as e:
        status["redis_cache"] = f"failed: {str(e)}"

    # 3. Redis Stream 연결 확인
    try:
        r_stream = aioredis.from_url(str(settings.REDIS_STREAM_URL), socket_timeout=3)
        await r_stream.ping()
        await r_stream.close()
        status["redis_stream"] = "connected"
    except Exception as e:
        status["redis_stream"] = f"failed: {str(e)}"

    return success_response(message="Health check completed.", data=status)
