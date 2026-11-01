"""Infrastructure clients against real PostgreSQL and S3-compatible storage (RustFS)."""

from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from testcontainers.community.postgres import PostgresContainer
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import HttpWaitStrategy

from audio_platform.api import create_app
from audio_platform.core.config import Settings
from audio_platform.core.container import build_container
from audio_platform.core.health import run_checks
from audio_platform.infrastructure.storage import s3_client
from tests.conftest import make_settings

pytestmark = pytest.mark.integration

S3_ACCESS_KEY, S3_SECRET_KEY = "it-access", "it-secret-key"
BUCKET = "it-recordings"


@pytest.fixture(scope="module")
def postgres_dsn() -> Iterator[str]:
    with PostgresContainer("postgres:18.6-alpine", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="module")
def s3_endpoint() -> Iterator[str]:
    container = (
        DockerContainer("rustfs/rustfs:1.0.4")
        .with_env("RUSTFS_ACCESS_KEY", S3_ACCESS_KEY)
        .with_env("RUSTFS_SECRET_KEY", S3_SECRET_KEY)
        .with_exposed_ports(9000)
        .waiting_for(HttpWaitStrategy(9000, "/health").for_status_code(200))
    )
    with container:
        yield f"http://{container.get_container_host_ip()}:{container.get_exposed_port(9000)}"


@pytest.fixture
def settings(
    postgres_dsn: str, s3_endpoint: str, monkeypatch: pytest.MonkeyPatch
) -> Settings:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", S3_ACCESS_KEY)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", S3_SECRET_KEY)
    return make_settings(
        postgres={"dsn": postgres_dsn},
        aws={
            "endpoint_url": s3_endpoint,
            "s3_addressing_style": "path",
            "region": "us-east-1",
        },
        storage={"bucket": BUCKET},
    )


@pytest.fixture
async def bucket(settings: Settings) -> AsyncIterator[str]:
    async with s3_client(settings.aws) as s3:
        existing = {b["Name"] for b in (await s3.list_buckets()).get("Buckets", [])}
        if BUCKET not in existing:
            await s3.create_bucket(Bucket=BUCKET)
    yield BUCKET


async def test_readiness_passes_against_real_postgres_and_s3(
    settings: Settings, bucket: str
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


async def test_ready_endpoint_with_the_real_container(
    settings: Settings, bucket: str
) -> None:
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
