from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import boto3
import pytest
from alembic import command
from alembic.config import Config
from botocore.config import Config as BotoConfig
from testcontainers.community.postgres import PostgresContainer
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import HttpWaitStrategy

from audio_platform.core.config import Settings, get_settings
from tests.conftest import make_settings

S3_ACCESS_KEY, S3_SECRET_KEY = "it-access", "it-secret-key"
BUCKET = "it-recordings"
REPO_ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def database_env(dsn: str) -> Iterator[None]:
    """migrations/env.py reads the DSN through Settings, like the real migrate job."""
    with pytest.MonkeyPatch.context() as env:
        env.setenv("AUDIO_POSTGRES__DSN", dsn)
        env.setenv("AUDIO_STORAGE__BUCKET", BUCKET)
        get_settings.cache_clear()
        try:
            yield
        finally:
            get_settings.cache_clear()


def alembic(*args: str, dsn: str) -> None:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    with database_env(dsn):
        match args:
            case ("upgrade", revision):
                command.upgrade(config, revision)
            case ("downgrade", revision):
                command.downgrade(config, revision)
            case ("check",):
                command.check(config)
            case _:
                raise ValueError(args)


@pytest.fixture(scope="session")
def postgres_dsn() -> Iterator[str]:
    with PostgresContainer("postgres:18.6-alpine", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def migrated_dsn(postgres_dsn: str) -> str:
    alembic("upgrade", "head", dsn=postgres_dsn)
    return postgres_dsn


@pytest.fixture(scope="session")
def s3_endpoint() -> Iterator[str]:
    container = (
        DockerContainer("rustfs/rustfs:1.0.4")
        .with_env("RUSTFS_ACCESS_KEY", S3_ACCESS_KEY)
        .with_env("RUSTFS_SECRET_KEY", S3_SECRET_KEY)
        .with_exposed_ports(9000)
        .waiting_for(HttpWaitStrategy(9000, "/health").for_status_code(200))
    )
    with container:
        endpoint = (
            f"http://{container.get_container_host_ip()}"
            f":{container.get_exposed_port(9000)}"
        )
        boto3.client(
            "s3",
            endpoint_url=endpoint,
            region_name="us-east-1",
            aws_access_key_id=S3_ACCESS_KEY,
            aws_secret_access_key=S3_SECRET_KEY,
            config=BotoConfig(s3={"addressing_style": "path"}),
        ).create_bucket(Bucket=BUCKET)
        yield endpoint


@pytest.fixture
def aws_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", S3_ACCESS_KEY)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", S3_SECRET_KEY)
    monkeypatch.delenv("AWS_PROFILE", raising=False)


@pytest.fixture
def settings(migrated_dsn: str, s3_endpoint: str, aws_credentials: None) -> Settings:
    return make_settings(
        postgres={"dsn": migrated_dsn},
        aws={
            "endpoint_url": s3_endpoint,
            "s3_addressing_style": "path",
            "region": "us-east-1",
        },
        storage={"bucket": BUCKET},
        upload={"part_size_bytes": 5 * 1024 * 1024},
    )
