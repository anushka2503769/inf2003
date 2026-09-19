"""A single error shape for every failed request.

The browser branches on `error.code`, so the code is part of the API contract
and must not be changed without updating frontend/src/types/api.ts.
"""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError
from starlette.exceptions import HTTPException as StarletteHTTPException

_STATUS_TO_CODE = {
    400: "validation_failed",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_failed",
    429: "rate_limited",
}


class ApiError(Exception):
    """Raised by route handlers to produce a coded error response."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def _envelope(
    status_code: int, code: str, message: str, details: dict[str, Any] | None = None
) -> JSONResponse:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=body)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _envelope(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(PyMongoError)
    async def _handle_mongo_error(_: Request, __: PyMongoError) -> JSONResponse:
        return _envelope(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "service_unavailable",
            "Document storage is temporarily unavailable.",
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_TO_CODE.get(exc.status_code, "internal_error")
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return _envelope(exc.status_code, code, detail)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Report the first problem only. The client shows one message per field
        # and a full pydantic error tree is not useful to a student.
        first = exc.errors()[0] if exc.errors() else None
        field = ".".join(str(part) for part in first["loc"][1:]) if first else ""
        message = first["msg"] if first else "The request body was not valid."
        return _envelope(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "validation_failed",
            message,
            {"field": field} if field else None,
        )
