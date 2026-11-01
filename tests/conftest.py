from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from audio_platform.api import create_app
from audio_platform.core.auth import DevHeaderAuthenticator
from audio_platform.core.config import Settings
from audio_platform.core.container import Container
from audio_platform.core.health import HealthCheck
from audio_platform.modules.recordings.domain import UploadPolicy
from audio_platform.modules.recordings.services import RecordingService
from tests.fakes.recordings import FakeAudioObjectStorage, InMemoryRecordingStore

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


def make_recording_service(
    settings: Settings,
    store: InMemoryRecordingStore,
    storage: FakeAudioObjectStorage,
    **kwargs: Any,
) -> RecordingService:
    upload = settings.upload
    return RecordingService(
        uow=store.unit_of_work,
        storage=storage,
        policy=UploadPolicy(
            max_size_bytes=upload.max_size_bytes,
            part_size_bytes=upload.part_size_bytes,
            allowed_content_types=frozenset(upload.allowed_content_types),
        ),
        url_ttl_s=upload.url_ttl_s,
        **kwargs,
    )


@pytest.fixture
def recordings_store() -> InMemoryRecordingStore:
    return InMemoryRecordingStore()


@pytest.fixture
def fake_storage() -> FakeAudioObjectStorage:
    return FakeAudioObjectStorage()


@pytest.fixture
def app(
    settings: Settings,
    health_checks: list[HealthCheck],
    recordings_store: InMemoryRecordingStore,
    fake_storage: FakeAudioObjectStorage,
) -> FastAPI:
    async def fake_container(s: Settings) -> Container:
        return Container(
            settings=s,
            resources=AsyncExitStack(),
            health_checks=tuple(health_checks),
            authenticator=DevHeaderAuthenticator(),
            recording_service=make_recording_service(s, recordings_store, fake_storage),
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
