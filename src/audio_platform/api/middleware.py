import re
import time
import uuid

import structlog
from fastapi import FastAPI
from starlette.datastructures import Headers, MutableHeaders
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from audio_platform.api.errors import error_response
from audio_platform.core.config import Settings
from audio_platform.core.logging import LogEvent, get_logger

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

logger = get_logger(__name__)


class RequestContextMiddleware:
    """
    Pure ASGI middleware (no BaseHTTPMiddleware) so streaming responses are not
    buffered.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get(REQUEST_ID_HEADER)
        request_id = (
            incoming
            if incoming and _VALID_REQUEST_ID.match(incoming)
            else uuid.uuid7().hex
        )
        scope.setdefault("state", {})["request_id"] = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        status_code = 500
        response_started = False
        started_at = time.perf_counter()

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            logger.exception(LogEvent.HTTP_UNHANDLED_ERROR)
            if response_started:
                raise
            response = error_response(
                500, "internal_error", "Internal server error", request_id
            )
            await response(scope, receive, send_with_request_id)
        finally:
            logger.info(
                LogEvent.HTTP_REQUEST_COMPLETED,
                method=scope["method"],
                path=scope["path"],
                status=status_code,
                duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
            )
            structlog.contextvars.clear_contextvars()


def install_middleware(app: FastAPI, settings: Settings) -> None:
    app.add_middleware(RequestContextMiddleware)
    # Added last = outermost, so 500s rendered by RequestContextMiddleware get CORS
    # headers too; otherwise browsers hide the error body behind a CORS error.
    if settings.api.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.api.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=[REQUEST_ID_HEADER],
        )
