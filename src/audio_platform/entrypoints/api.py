"""API process entrypoint: `audio-platform-api` (prod) or `make run` (dev, hot reload)."""

import sys

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel, ValidationError

from audio_platform.api.app import create_app
from audio_platform.core.config import Settings, get_settings
from audio_platform.core.logging import configure_logging


def _env_var_hint(loc: tuple[int | str, ...]) -> str:
    name = "AUDIO_" + "__".join(str(part).upper() for part in loc)
    field = Settings.model_fields.get(str(loc[0])) if len(loc) == 1 else None
    is_group = field is not None and isinstance(field.annotation, type) and issubclass(field.annotation, BaseModel)
    return f"{name}__*" if is_group else name


def load_settings_or_exit() -> Settings:
    """Fail fast: print one line per bad setting and exit before any socket is opened."""
    try:
        return get_settings()
    except ValidationError as exc:
        for error in exc.errors(include_input=False):
            path = ".".join(str(part) for part in error["loc"])
            print(f"config error: {path} ({_env_var_hint(error['loc'])}): {error['msg']}", file=sys.stderr)
        raise SystemExit(2) from None


def app_factory() -> FastAPI:
    """Used by `uvicorn --factory` in development."""
    settings = load_settings_or_exit()
    configure_logging(settings)
    return create_app(settings)


def main() -> None:
    settings = load_settings_or_exit()
    configure_logging(settings)
    uvicorn.run(
        create_app(settings),
        host=settings.api.host,
        port=settings.api.port,
        log_config=None,  # keep our structured logging configuration
        access_log=False,  # RequestContextMiddleware logs every request with its request_id
        timeout_graceful_shutdown=20,
    )


if __name__ == "__main__":
    main()
