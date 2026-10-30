import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.domain.errors import (
    AuthenticationFailed,
    Conflict,
    DomainError,
    InvalidRequest,
    NotFound,
    PermissionDenied,
)

logger = logging.getLogger(__name__)

STATUS_CODES = {
    AuthenticationFailed: 401,
    PermissionDenied: 403,
    NotFound: 404,
    Conflict: 409,
    InvalidRequest: 422,
}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if isinstance(exc, AuthenticationFailed) else None
        return JSONResponse(
            status_code=STATUS_CODES.get(type(exc), 400),
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
            headers=headers,
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "Something went wrong on our side", "details": {}}},
        )
