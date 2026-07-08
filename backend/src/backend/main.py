from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.chat_api import chat_router
from .api.check_db_conn import health_router
from .api.sse_api import sse_router
from .api.user_api import user_router
from .api.webhook_api import webhook_router
from .core.config import CORS_OPTIONS, configure_app
from .core.exceptions import exception_handlers
from .db.redis import close_redis_pools


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Perform startup tasks here (e.g., connect to database, initialize resources)
    yield  # 제어권 넘기는 제너레이터
    # 종료 시: Redis 커넥션 풀 소켓 정리 (SSE 스트림/캐시 풀 graceful shutdown)
    await close_redis_pools()


app = FastAPI(
    lifespan=lifespan,
    exception_handlers=exception_handlers,
    title="RealFinancial Backend",
    version="0.1.0",
)

app.include_router(user_router, prefix="/api/v1")
app.include_router(health_router, prefix="/api/v1")
app.include_router(sse_router, prefix="/api/v1")
app.include_router(webhook_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")

configure_app(app)  # 일괄적인 설정값 주입

# CORS 설정은 앱 전체의 가장 바깥에 둬서
# 검증 / 서버 에러 응답에도 헤더가 붙게 한다.
app.add_middleware(CORSMiddleware, **CORS_OPTIONS)


@app.get("/")
def read_root():
    return {"message": "안녕하세요!"}
