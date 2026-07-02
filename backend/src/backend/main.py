from contextlib import asynccontextmanager

from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Perform startup tasks here (e.g., connect to database, initialize resources)
    yield  # 제어권 넘기는 제너레이터
    # Perform shutdown tasks here (e.g., close database connections, cleanup resources)


app = FastAPI(lifespan=lifespan, title="RealFinancial Backend", version="0.1.0")
