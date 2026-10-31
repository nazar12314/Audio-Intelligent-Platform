"""One error envelope for every failure: {"error": {"code", "message", "request_id", "details"?}}."""

from collections.abc import Mapping
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from audio_platform.core.exceptions import AppError

_HTTP_CODES = {
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    413: "payload_too_large",
}


def error_response(
    status_code: int,
    code: str,
    message: str,
    request_id: str | None,
    details: dict[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    error: dict[str, Any] = {"code": code, "message": message, "request_id": request_id}
    if details:
        error["details"] = details
    return JSONResponse({"error": error}, status_code=status_code, headers=headers)


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


async def _app_error(request: Request, exc: Exception) -> JSONResponse:
    error = cast(AppError, exc)  # registered for AppError only
    return error_response(error.status_code, error.code, error.message, _request_id(request), error.details)


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    validation = cast(RequestValidationError, exc)
    # `input` is deliberately dropped: it may echo secrets or large payloads back to the client.
    errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in validation.errors()]
    return error_response(
        422, "validation_failed", "Request validation failed", _request_id(request), {"errors": errors}
    )


async def _http_error(request: Request, exc: Exception) -> JSONResponse:
    http = cast(StarletteHTTPException, exc)
    code = _HTTP_CODES.get(http.status_code, "http_error")
    return error_response(http.status_code, code, str(http.detail), _request_id(request), headers=http.headers)


def install_exception_handlers(app: FastAPI) -> None:
    """Unhandled exceptions are rendered by RequestContextMiddleware, which owns the request ID."""
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
