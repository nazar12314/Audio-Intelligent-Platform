from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from audio_platform import __version__
from audio_platform.api.errors import install_exception_handlers
from audio_platform.api.health import health_router
from audio_platform.api.middleware import install_middleware
from audio_platform.core.config import Settings, get_settings
from audio_platform.core.container import Container, build_container
from audio_platform.core.logging import LogEvent, get_logger
from audio_platform.modules.processing.api import processing_router
from audio_platform.modules.recordings.api import recordings_router

ContainerFactory = Callable[[Settings], Awaitable[Container]]

logger = get_logger(__name__)


def build_api_router() -> APIRouter:
    router = APIRouter()
    router.include_router(health_router)

    v1 = APIRouter(prefix="/api/v1")
    v1.include_router(recordings_router)
    v1.include_router(processing_router)
    router.include_router(v1)
    return router


def create_app(
    settings: Settings | None = None,
    *,
    container_factory: ContainerFactory = build_container,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info(LogEvent.APP_STARTING, env=settings.env, version=__version__)
        container = await container_factory(settings)
        app.state.container = container
        async with container.resources:  # closes clients in reverse order of opening
            yield
        logger.info(LogEvent.APP_STOPPED)

    app = FastAPI(
        title=settings.service_name,
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    install_middleware(app, settings)
    install_exception_handlers(app)
    app.include_router(build_api_router())
    return app
