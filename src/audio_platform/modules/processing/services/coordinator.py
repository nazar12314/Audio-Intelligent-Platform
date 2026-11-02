import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from audio_platform.core.logging import LogEvent, get_logger
from audio_platform.core.messaging import Destinations, Event
from audio_platform.modules.processing.domain import ProcessingJob, StageName
from audio_platform.modules.processing.ports import ProcessingUnitOfWorkFactory

logger = get_logger(__name__)


class EventTypes:
    RECORDING_UPLOADED = "recordings.recording.uploaded"
    VAD_REQUESTED = "processing.vad.requested"
    VAD_COMPLETED = "processing.vad.completed"
    VAD_FAILED = "processing.vad.failed"
    ASR_REQUESTED = "processing.asr.requested"
    ASR_COMPLETED = "processing.asr.completed"
    ASR_FAILED = "processing.asr.failed"


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
        now = self._clock()

        async with self._uow() as uow:
            job = await uow.jobs.get(UUID(data["job_id"]), for_update=True)
            if job is None or job.is_finished or StageName.ASR in job.stages:
                return

            job.record_speech(speech_detected, now=now)
            if speech_detected:
                job.add_stage(StageName.ASR, now=now)
                await uow.outbox.add(
                    Event.new(EventTypes.ASR_REQUESTED, {"job_id": str(job.id)}),
                    destination=Destinations.ASR_TASKS,
                )
            else:
                job.complete(now=now)
            await uow.jobs.update(job)
            await uow.commit()

        if speech_detected:
            logger.info(
                LogEvent.PROCESSING_STAGE_REQUESTED,
                job_id=str(job.id),
                stage=StageName.ASR.value,
            )
        else:
            logger.info(
                LogEvent.PROCESSING_JOB_COMPLETED,
                job_id=str(job.id),
                speech_detected=False,
            )

    async def vad_failed(self, data: dict[str, Any]) -> None:
        await self._fail(UUID(data["job_id"]), f"vad: {data['error']}")

    async def asr_completed(self, data: dict[str, Any]) -> None:
        async with self._uow() as uow:
            job = await uow.jobs.get(UUID(data["job_id"]), for_update=True)
            if job is None or job.is_finished:
                return

            job.complete(now=self._clock())
            await uow.jobs.update(job)
            await uow.commit()

        logger.info(
            LogEvent.PROCESSING_JOB_COMPLETED,
            job_id=str(job.id),
            speech_detected=True,
            language=data.get("language"),
        )

    async def asr_failed(self, data: dict[str, Any]) -> None:
        await self._fail(UUID(data["job_id"]), f"asr: {data['error']}")

    async def _fail(self, job_id: UUID, reason: str) -> None:
        async with self._uow() as uow:
            job = await uow.jobs.get(job_id, for_update=True)
            if job is None or job.is_finished:
                return

            job.fail(reason, now=self._clock())
            await uow.jobs.update(job)
            await uow.commit()

        logger.warning(
            LogEvent.PROCESSING_JOB_FAILED,
            job_id=str(job.id),
            reason=job.failure_reason,
        )
