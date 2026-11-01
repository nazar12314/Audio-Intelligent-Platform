from contextlib import AsyncExitStack
from dataclasses import dataclass
from functools import partial

from audio_platform.core.auth import Authenticator, DevHeaderAuthenticator
from audio_platform.core.config import Settings
from audio_platform.core.health import HealthCheck
from audio_platform.infrastructure.db.sql import ping, session_factory, sql_engine
from audio_platform.infrastructure.storage.s3 import ping_bucket, s3_client
from audio_platform.modules.recordings.adapters import (
    S3AudioObjectStorage,
    SqlRecordingUnitOfWork,
)
from audio_platform.modules.recordings.domain import UploadPolicy
from audio_platform.modules.recordings.services import RecordingService


@dataclass(frozen=True, slots=True)
class Container:
    settings: Settings
    resources: AsyncExitStack  # every opened client is closed on shutdown
    health_checks: tuple[HealthCheck, ...]
    authenticator: Authenticator
    recording_service: RecordingService


async def build_container(settings: Settings) -> Container:
    stack = AsyncExitStack()
    try:
        engine = await stack.enter_async_context(
            sql_engine(settings.postgres, application_name=settings.service_name)
        )
        s3 = await stack.enter_async_context(s3_client(settings.aws))
        presigner = s3
        if settings.storage.public_endpoint_url:
            presigner = await stack.enter_async_context(
                s3_client(
                    settings.aws, endpoint_url=settings.storage.public_endpoint_url
                )
            )
    except BaseException:
        await stack.aclose()
        raise

    sessions = session_factory(engine)
    upload = settings.upload
    recording_service = RecordingService(
        uow=lambda: SqlRecordingUnitOfWork(sessions),
        storage=S3AudioObjectStorage(s3, presigner, settings.storage.bucket),
        policy=UploadPolicy(
            max_size_bytes=upload.max_size_bytes,
            part_size_bytes=upload.part_size_bytes,
            allowed_content_types=frozenset(upload.allowed_content_types),
        ),
        url_ttl_s=upload.url_ttl_s,
    )
    health_checks = (
        HealthCheck("postgres", partial(ping, engine)),
        HealthCheck("s3", partial(ping_bucket, s3, settings.storage.bucket)),
    )
    return Container(
        settings=settings,
        resources=stack,
        health_checks=health_checks,
        authenticator=DevHeaderAuthenticator(),
        recording_service=recording_service,
    )
