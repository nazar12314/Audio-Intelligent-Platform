from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from audio_platform.core.logging import LogEvent, get_logger
from audio_platform.core.messaging import Destinations, Event
from audio_platform.modules.processing.domain import (
    InvalidAudio,
    ProcessingJob,
    StageName,
)
from audio_platform.modules.processing.ports import (
    ProcessingUnitOfWork,
    ProcessingUnitOfWorkFactory,
)

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def artifact_key(object_key: str, name: str) -> str:
    """Artifacts sit next to the original: users/<owner>/recordings/<id>/<name>."""
    return f"{object_key.rsplit('/', 1)[0]}/{name}"


@dataclass(frozen=True, slots=True)
class StageOutcome:
    result: dict[str, Any]  # stored with the stage
    event_data: dict[str, Any] = field(default_factory=dict)  # added to the event


Work = Callable[[ProcessingJob], Awaitable[StageOutcome]]


class StageTask:
    """
    Runs one stage of one job for a stage worker. Storage and CPU work happen
    outside any transaction; the outcome and its event are committed together, so
    the coordinator hears about every outcome exactly as recorded. Redelivered
    tasks whose outcome is already recorded do nothing.
    """

    def __init__(
        self,
        uow: ProcessingUnitOfWorkFactory,
        stage: StageName,
        *,
        completed_event: str,
        failed_event: str,
        max_attempts: int,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._uow = uow
        self._stage = stage
        self._completed_event = completed_event
        self._failed_event = failed_event
        self._max_attempts = max_attempts
        self._clock = clock

    async def run(
        self, data: dict[str, Any], *, receive_count: int, work: Work
    ) -> None:
        job = await self._claim(UUID(data["job_id"]))
        if job is None:
            return
        logger.info(
            LogEvent.STAGE_STARTED,
            stage=self._stage.value,
            job_id=str(job.id),
            attempt=receive_count,
        )
        try:
            outcome = await work(job)
        except InvalidAudio as exc:
            await self._finish_failed(job.id, f"invalid audio: {exc}")
            return
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            if receive_count >= self._max_attempts:
                await self._finish_failed(
                    job.id, f"gave up after {receive_count} attempts ({error})"
                )
                return
            await self._record_retryable_error(job.id, error)
            logger.warning(
                LogEvent.STAGE_RETRY_SCHEDULED,
                stage=self._stage.value,
                job_id=str(job.id),
                attempt=receive_count,
            )
            raise  # the message stays in the queue and is redelivered
        await self._finish_succeeded(job.id, outcome)

    async def _open_job(
        self, uow: ProcessingUnitOfWork, job_id: UUID
    ) -> ProcessingJob | None:
        """The locked job, or None when this stage has nothing left to do."""
        job = await uow.jobs.get(job_id, for_update=True)
        if (
            job is None
            or job.is_finished
            or self._stage not in job.stages
            or job.stage(self._stage).is_finished
        ):
            return None
        return job

    async def _claim(self, job_id: UUID) -> ProcessingJob | None:
        async with self._uow() as uow:
            job = await self._open_job(uow, job_id)
            if job is None:
                return None
            job.begin_stage(self._stage, now=self._clock())
            await uow.jobs.update(job)
            await uow.commit()
        return job

    async def _finish_succeeded(self, job_id: UUID, outcome: StageOutcome) -> None:
        async with self._uow() as uow:
            job = await self._open_job(uow, job_id)
            if job is None:
                return
            job.succeed_stage(self._stage, outcome.result, now=self._clock())
            await uow.jobs.update(job)
            await uow.outbox.add(
                Event.new(
                    self._completed_event,
                    {"job_id": str(job_id), **outcome.event_data},
                ),
                destination=Destinations.PIPELINE_EVENTS,
            )
            await uow.commit()
        logger.info(
            LogEvent.STAGE_COMPLETED,
            stage=self._stage.value,
            job_id=str(job_id),
            **outcome.event_data,
        )

    async def _finish_failed(self, job_id: UUID, error: str) -> None:
        async with self._uow() as uow:
            job = await self._open_job(uow, job_id)
            if job is None:
                return
            job.fail_stage(self._stage, error, now=self._clock())
            await uow.jobs.update(job)
            await uow.outbox.add(
                Event.new(self._failed_event, {"job_id": str(job_id), "error": error}),
                destination=Destinations.PIPELINE_EVENTS,
            )
            await uow.commit()
        logger.warning(
            LogEvent.STAGE_FAILED,
            stage=self._stage.value,
            job_id=str(job_id),
            error=error,
        )

    async def _record_retryable_error(self, job_id: UUID, error: str) -> None:
        async with self._uow() as uow:
            job = await self._open_job(uow, job_id)
            if job is None:
                return
            job.record_retryable_error(self._stage, error, now=self._clock())
            await uow.jobs.update(job)
            await uow.commit()
