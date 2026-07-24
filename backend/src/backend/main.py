import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.account_api import account_router
from .api.agent_tools import agent_tools_router
from .api.chat_api import chat_router
from .api.check_db_conn import health_router
from .api.recipient_candidate_api import recipient_candidate_router
from .api.sse_api import sse_router
from .api.ui_api import ui_router
from .api.user_api import user_router
from .api.webhook_api import webhook_router
from .core.config import CORS_OPTIONS, configure_app
from .core.exceptions import exception_handlers
from .core.logging_config import setup_logging
from .db.redis import close_redis_pools
from .migration.migration import run_migrations
from .services.agent_client import close_agent_client
from .services.financial import close_financial_client

# 앱 부팅 시 1회: 로깅(콘솔/파일 로테이션) 설정을 먼저 적용해 이후 로그가 유실되지 않게 한다.
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Perform startup tasks here (e.g., connect to database, initialize resources)
    run_migrations()
    logger.info("마이그레이션 적용 완료")
    yield  # 제어권 넘기는 제너레이터
    # 종료 시: Redis 커넥션 풀 + 계정계 HTTP 클라이언트 graceful shutdown
    await close_redis_pools()
    await close_financial_client()
    await close_agent_client()
    logger.info("레디스 풀 종료 완료, 계정계·Agent HTTP 클라이언트 종료 완료")


app = FastAPI(
    lifespan=lifespan,
    exception_handlers=exception_handlers,
    title="RealFinancial Backend",
    version="0.1.0",
)

app.include_router(user_router, prefix="/api/v1")
app.include_router(account_router, prefix="/api/v1")
app.include_router(health_router, prefix="/api/v1")
app.include_router(sse_router, prefix="/api/v1")
app.include_router(webhook_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(ui_router, prefix="/api/v1")
app.include_router(recipient_candidate_router, prefix="/api/v1")
app.include_router(agent_tools_router, prefix="/api/v1")

configure_app(app)  # 일괄적인 설정값 주입

# CORS 설정은 앱 전체의 가장 바깥에 둬서
# 검증 / 서버 에러 응답에도 헤더가 붙게 한다.
app.add_middleware(CORSMiddleware, **CORS_OPTIONS)


@app.get("/")
def read_root():
    return {"message": "안녕하세요!"}


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "backend",
        "version": "0.1.0",
    }
