"""FastAPI application factory and phase-one error handling."""

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src import models  # noqa: F401
from src.api import ai, attributes, products
from src.database import Base, engine
from src.services.pim_service import ConflictError, NotFoundError, PimError


def create_app(create_tables: bool = True) -> FastAPI:
    """Create the application and optionally initialize database tables."""
    if create_tables:
        Base.metadata.create_all(bind=engine)
    app = FastAPI(title="Woo PIM AI", version="0.1.0")
    app.include_router(products.router)
    app.include_router(attributes.router)
    app.include_router(ai.router)

    @app.exception_handler(PimError)
    async def pim_error_handler(request: Request, exc: PimError) -> JSONResponse:
        del request
        code = 404 if isinstance(exc, NotFoundError) else 409 if isinstance(exc, ConflictError) else 422
        return JSONResponse(status_code=code, content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}})

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        del request
        return JSONResponse(status_code=422, content=jsonable_encoder({"error": {"code": "validation_error", "message": "Request validation failed", "details": exc.errors()}}))

    return app


app = create_app()
