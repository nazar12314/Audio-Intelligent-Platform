import asyncio
from collections.abc import Callable, Coroutine
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import timedelta
from functools import partial
from typing import Any, Literal

from audio_platform.core.auth import Authenticator, DevHeaderAuthenticator
from audio_platform.core.config import Settings
from audio_platform.core.health import HealthCheck
from audio_platform.core.messaging import Destinations
from audio_platform.infrastructure.db.outbox import OutboxCleaner, OutboxRelay
from audio_platform.infrastructure.db.sql import ping, session_factory, sql_engine
from audio_platform.infrastructure.messaging import (
    SqsConsumer,
    SqsPublisher,
    resolve_queue_urls,
    sqs_client,
)
from audio_platform.infrastructure.storage.s3 import ping_bucket, s3_client
from audio_platform.modules.processing.adapters import (
    S3ArtifactStorage,
    SqlProcessingUnitOfWork,
)
from audio_platform.modules.processing.consumers import (
    PipelineEventsConsumer,
    VadTasksConsumer,
)
from audio_platform.modules.processing.domain import VadParameters
from audio_platform.modules.processing.services import (
    PipelineCoordinator,
    ProcessingQueries,
    VadWorker,
    VadWorkerConfig,
)
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
    processing_queries: ProcessingQueries


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
    processing_queries = ProcessingQueries(
        uow=lambda: SqlProcessingUnitOfWork(sessions),
        storage=S3ArtifactStorage(s3, settings.storage.bucket),
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
        processing_queries=processing_queries,
    )


WorkerRole = Literal["pipeline", "vad"]
Runner = Callable[[asyncio.Event], Coroutine[Any, Any, None]]


@dataclass(frozen=True, slots=True)
class WorkerRuntime:
    resources: AsyncExitStack
    runners: tuple[Runner, ...]


async def build_worker(settings: Settings, role: WorkerRole) -> WorkerRuntime:
    """
    `pipeline`: outbox relay + coordinator. `vad`: VAD task consumer, scaled by
    running more processes.
    """
    stack = AsyncExitStack()
    try:
        engine = await stack.enter_async_context(
            sql_engine(
                settings.postgres, application_name=f"{settings.service_name}-{role}"
            )
        )
        sqs = await stack.enter_async_context(
            sqs_client(settings.aws, settings.messaging)
        )
        queues = await resolve_queue_urls(
            sqs,
            {
                Destinations.PIPELINE_EVENTS: settings.messaging.pipeline_events_queue,
                Destinations.VAD_TASKS: settings.messaging.vad_tasks_queue,
            },
        )
        s3 = await stack.enter_async_context(s3_client(settings.aws))
    except BaseException:
        await stack.aclose()
        raise

    sessions = session_factory(engine)
    messaging = settings.messaging

    def uow() -> SqlProcessingUnitOfWork:
        return SqlProcessingUnitOfWork(sessions)

    def consumer(
        destination: str, handler: PipelineEventsConsumer | VadTasksConsumer
    ) -> Runner:
        return SqsConsumer(
            sqs,
            queues[destination],
            handler,
            name=destination,
            wait_time_s=messaging.wait_time_s,
            visibility_timeout_s=messaging.visibility_timeout_s,
            handler_timeout_s=messaging.handler_timeout_s,
        ).run

    if role == "pipeline":
        relay = OutboxRelay(
            sessions,
            SqsPublisher(sqs, queues),
            batch_size=messaging.relay_batch_size,
            interval_s=messaging.relay_interval_s,
        )
        coordinator = PipelineCoordinator(uow)
        runners: tuple[Runner, ...] = (
            relay.run,
            OutboxCleaner(
                sessions,
                retention=timedelta(days=messaging.outbox_retention_days),
                interval_s=messaging.outbox_cleanup_interval_s,
            ).run,
            consumer(Destinations.PIPELINE_EVENTS, PipelineEventsConsumer(coordinator)),
        )
    else:
        # The child process imports the heavy `processing` extra, not the worker.
        from audio_platform.modules.processing.adapters.analyzer import (
            SubprocessAudioAnalyzer,
        )

        processing = settings.processing
        worker = VadWorker(
            uow,
            S3ArtifactStorage(s3, settings.storage.bucket),
            SubprocessAudioAnalyzer(timeout_s=settings.processing.analysis_timeout_s),
            VadWorkerConfig(
                params=VadParameters(
                    threshold=processing.vad_threshold,
                    min_speech_ms=processing.vad_min_speech_ms,
                    min_silence_ms=processing.vad_min_silence_ms,
                    speech_pad_ms=processing.vad_speech_pad_ms,
                ),
                max_duration_s=processing.max_duration_s,
                max_attempts=messaging.max_attempts,
            ),
        )
        runners = (consumer(Destinations.VAD_TASKS, VadTasksConsumer(worker)),)
    return WorkerRuntime(resources=stack, runners=runners)
