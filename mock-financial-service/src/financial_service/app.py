"""FastAPI application factory with custom error handler."""

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse

from .analytics_router import analytics_router
from .card_router import card_router
from .database import Base, engine
from .migrations import apply_analytics_views, apply_audit_triggers, apply_snapshot_schema
from .routers import router


def create_app() -> FastAPI:
    app = FastAPI(title="Mock Financial Service", version="0.1.0")

    # Create tables + triggers + analytics views on startup
    @app.on_event("startup")
    def startup():
        Base.metadata.create_all(bind=engine)
        apply_audit_triggers(engine)
        apply_analytics_views(engine)
        apply_snapshot_schema(engine)

    # Pydantic validation errors → fixed {error_code, message} schema
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        return JSONResponse(
            status_code=422,
            content={"error_code": "VALIDATION_ERROR", "message": str(exc)},
        )

    # HTTPException raised by routers → fixed schema if detail is dict
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        if isinstance(exc.detail, dict) and "error_code" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error_code": "HTTP_ERROR", "message": str(exc.detail)},
        )

    app.include_router(router, prefix="/api/v1")
    app.include_router(card_router, prefix="/api/v1")
    app.include_router(analytics_router, prefix="/api/v1")
    return app


app = create_app()
