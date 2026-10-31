"""Transport layer: app factory, middleware, error handlers, shared dependencies."""

from audio_platform.api.app import build_api_router, create_app

__all__ = ["build_api_router", "create_app"]
