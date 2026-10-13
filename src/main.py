"""FastAPI application factory and phase-one error handling."""

import logging
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles

from src import models  # noqa: F401
from src.api import ai, attributes, products, sync
from src.database import Base, engine
from src.integrations.fake_woo import FakeWooStore
from src.services.pim_service import ConflictError, NotFoundError, PimError

logger = logging.getLogger("pim.api")
STATIC_DIR = Path(__file__).parent / "static"


def create_app(create_tables: bool = True) -> FastAPI:
    """Create the application and optionally initialize database tables."""
    if create_tables:
        Base.metadata.create_all(bind=engine)
    app = FastAPI(title="Woo PIM AI", version="0.1.0")
    app.state.fake_woo_store = FakeWooStore()
    app.include_router(products.router)
    app.include_router(attributes.router)
    app.include_router(ai.router)
    app.include_router(sync.router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def home() -> FileResponse:
        """Serve the browser-based catalog dashboard."""
        return FileResponse(STATIC_DIR / "index.html")

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        """Log request method, path, status, and elapsed milliseconds."""
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("request failed method=%s path=%s status=500", request.method, request.url.path)
            raise
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info("request method=%s path=%s status=%s elapsed_ms=%.1f", request.method, request.url.path, response.status_code, elapsed_ms)
        return response

    @app.exception_handler(PimError)
    async def pim_error_handler(request: Request, exc: PimError) -> JSONResponse:
        del request
        code = 404 if isinstance(exc, NotFoundError) else 409 if isinstance(exc, ConflictError) else 422
        return JSONResponse(status_code=code, content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}})

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        del request
        return JSONResponse(status_code=422, content=jsonable_encoder({"error": {"code": "validation_error", "message": "Request validation failed", "details": exc.errors()}}))

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        del request
        code = "not_found" if exc.status_code == 404 else "http_error"
        return JSONResponse(status_code=exc.status_code, content=jsonable_encoder({"error": {"code": code, "message": str(exc.detail), "details": None}}), headers=exc.headers)

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled application error path=%s", request.url.path,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return JSONResponse(status_code=500, content={"error": {"code": "internal_error", "message": "An unexpected error occurred", "details": None}})

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        """Report service health after a simple database connectivity check."""
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok"}

    return app


app = create_app()
