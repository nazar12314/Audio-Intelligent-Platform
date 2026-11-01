"""Infrastructure clients against real PostgreSQL and S3-compatible storage (RustFS)."""

import httpx
import pytest

from audio_platform.api import create_app
from audio_platform.core.config import Settings
from audio_platform.core.container import build_container
from audio_platform.core.health import run_checks

pytestmark = pytest.mark.integration


async def test_readiness_passes_against_real_postgres_and_s3(
    settings: Settings,
) -> None:
    container = await build_container(settings)
    async with container.resources:
        report = await run_checks(container.health_checks, timeout_s=5)
    assert report.status == "ok", report


async def test_readiness_fails_when_bucket_is_missing(settings: Settings) -> None:
    container = await build_container(
        settings.model_copy(
            update={
                "storage": settings.storage.model_copy(
                    update={"bucket": "missing-bucket"}
                )
            }
        )
    )
    async with container.resources:
        report = await run_checks(container.health_checks, timeout_s=5)
    assert report.status == "fail"
    assert {c.name for c in report.checks if not c.ok} == {"s3"}


async def test_ready_endpoint_with_the_real_container(settings: Settings) -> None:
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client,
    ):
        response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["checks"]["postgres"]["status"] == "ok"
