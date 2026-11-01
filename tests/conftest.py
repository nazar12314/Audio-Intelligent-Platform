from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from audio_platform.api import create_app
from audio_platform.core.config import Settings
from audio_platform.core.container import Container
from audio_platform.core.health import HealthCheck

TEST_DSN = "postgresql+asyncpg://test:test@localhost:5432/test"


def make_settings(**overrides: Any) -> Settings:
    """Settings for tests: never reads the developer's .env file."""
    values: dict[str, Any] = {
        "env": "test",
        "log_format": "console",
        "postgres": {"dsn": TEST_DSN},
        "storage": {"bucket": "test-recordings"},
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def health_checks() -> list[HealthCheck]:
    """Override in a test module to control what /health/ready sees."""
    return []


@pytest.fixture
def app(settings: Settings, health_checks: list[HealthCheck]) -> FastAPI:
    async def fake_container(s: Settings) -> Container:
        return Container(
            settings=s, resources=AsyncExitStack(), health_checks=tuple(health_checks)
        )

    return create_app(settings, container_factory=fake_container)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client,
    ):
        yield client


def probe_ok() -> Callable[[], Any]:
    async def probe() -> None:
        return None

    return probe


def probe_raising(exc: Exception) -> Callable[[], Any]:
    async def probe() -> None:
        raise exc

    return probe
