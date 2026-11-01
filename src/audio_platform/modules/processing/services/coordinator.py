import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from audio_platform.core.logging import LogEvent, get_logger
from audio_platform.core.messaging import Destinations, Event
from audio_platform.modules.processing.domain import ProcessingJob
from audio_platform.modules.processing.ports import ProcessingUnitOfWorkFactory

logger = get_logger(__name__)


class EventTypes:
    RECORDING_UPLOADED = "recordings.recording.uploaded"
    VAD_REQUESTED = "processing.vad.requested"
    VAD_COMPLETED = "processing.vad.completed"
    VAD_FAILED = "processing.vad.failed"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PipelineCoordinator:
    """
    Decides the next pipeline step from events. Every handler is idempotent: the
    broker delivers at least once, so repeats find the work already done.
    """

    def __init__(
        self,
        uow: ProcessingUnitOfWorkFactory,
        *,
        clock: Callable[[], datetime] = _utcnow,
        new_id: Callable[[], UUID] = uuid.uuid7,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._new_id = new_id

    async def recording_uploaded(self, data: dict[str, Any]) -> None:
        recording_id = UUID(data["recording_id"])
        async with self._uow() as uow:
            if await uow.jobs.find_by_recording(recording_id) is not None:
                return
            job = ProcessingJob.start(
                job_id=self._new_id(),
                recording_id=recording_id,
                owner_id=UUID(data["owner_id"]),
                object_key=data["object_key"],
                now=self._clock(),
            )
            await uow.jobs.add(job)
            await uow.outbox.add(
                Event.new(EventTypes.VAD_REQUESTED, {"job_id": str(job.id)}),
                destination=Destinations.VAD_TASKS,
            )
            await uow.commit()
        logger.info(
            LogEvent.PROCESSING_JOB_CREATED,
            job_id=str(job.id),
            recording_id=str(recording_id),
        )

    async def vad_completed(self, data: dict[str, Any]) -> None:
        speech_detected = bool(data["speech_detected"])
        async with self._uow() as uow:
            job = await uow.jobs.get(UUID(data["job_id"]), for_update=True)
            if job is None or job.is_finished:
                return
            # Transcription is the next stage once it exists; until then a job with
            # speech is complete after VAD, exactly like one without.
            job.complete(speech_detected=speech_detected, now=self._clock())
            await uow.jobs.update(job)
            await uow.commit()
        logger.info(
            LogEvent.PROCESSING_JOB_COMPLETED,
            job_id=str(job.id),
            speech_detected=speech_detected,
        )

    async def vad_failed(self, data: dict[str, Any]) -> None:
        async with self._uow() as uow:
            job = await uow.jobs.get(UUID(data["job_id"]), for_update=True)
            if job is None or job.is_finished:
                return
            job.fail(f"vad: {data['error']}", now=self._clock())
            await uow.jobs.update(job)
            await uow.commit()
        logger.warning(
            LogEvent.PROCESSING_JOB_FAILED,
            job_id=str(job.id),
            reason=job.failure_reason,
        )
