import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import text

from audio_platform.core.config import Settings
from audio_platform.core.exceptions import DependencyUnavailable
from audio_platform.infrastructure.db import session_factory, sql_engine
from audio_platform.infrastructure.storage import s3_client
from audio_platform.modules.recordings.adapters import (
    S3AudioObjectStorage,
    SqlRecordingUnitOfWork,
)
from audio_platform.modules.recordings.ports import UnitOfWorkFactory
from tests.contracts.recordings import (
    AudioObjectStorageContract,
    Downloader,
    PartUploader,
    RecordingUnitOfWorkContract,
)

pytestmark = pytest.mark.integration


class TestS3AudioObjectStorage(AudioObjectStorageContract):
    @pytest.fixture
    async def storage(self, settings: Settings) -> AsyncIterator[S3AudioObjectStorage]:
        async with s3_client(settings.aws) as client:
            yield S3AudioObjectStorage(client, client, settings.storage.bucket)

    @pytest.fixture
    async def upload_part(self) -> AsyncIterator[PartUploader]:
        async with httpx.AsyncClient() as http:

            async def upload(url: str, data: bytes) -> str:
                response = await http.put(url, content=data)
                response.raise_for_status()
                return response.headers["etag"]

            yield upload

    @pytest.fixture
    async def download(self) -> AsyncIterator[Downloader]:
        async with httpx.AsyncClient() as http:

            async def get(url: str) -> bytes:
                response = await http.get(url)
                response.raise_for_status()
                return response.content

            yield get


class TestSqlRecordingUnitOfWork(RecordingUnitOfWorkContract):
    @pytest.fixture
    async def uow(self, settings: Settings) -> AsyncIterator[UnitOfWorkFactory]:
        async with sql_engine(settings.postgres, application_name="tests") as engine:
            async with engine.begin() as connection:
                await connection.execute(text("TRUNCATE recordings"))
            sessions = session_factory(engine)
            yield lambda: SqlRecordingUnitOfWork(sessions)


async def test_exhausted_connection_pool_is_a_dependency_error(
    settings: Settings,
) -> None:
    postgres = settings.postgres.model_copy(
        update={"pool_size": 1, "max_overflow": 0, "pool_timeout_s": 0.2}
    )
    async with (
        sql_engine(postgres, application_name="tests") as engine,
        engine.connect(),  # holds the only pooled connection
    ):
        uow = SqlRecordingUnitOfWork(session_factory(engine))
        with pytest.raises(DependencyUnavailable):
            async with uow as tx:
                await tx.recordings.get_for_owner(uuid.uuid7(), uuid.uuid7())
