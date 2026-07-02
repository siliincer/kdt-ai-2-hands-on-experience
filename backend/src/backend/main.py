from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.test_api import user_router
from .core.exceptions import exception_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Perform startup tasks here (e.g., connect to database, initialize resources)
    yield  # 제어권 넘기는 제너레이터
    # Perform shutdown tasks here (e.g., close database connections, cleanup resources)


app = FastAPI(
    lifespan=lifespan,
    exception_handlers=exception_handlers,
    title="RealFinancial Backend",
    version="0.1.0",
)

app.include_router(user_router, prefix="/api/v1")


@app.get("/")
def read_root():
    return {"message": "안녕하세요!"}
