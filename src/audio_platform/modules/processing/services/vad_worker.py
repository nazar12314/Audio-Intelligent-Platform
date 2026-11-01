import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from audio_platform.core.logging import LogEvent, get_logger
from audio_platform.core.messaging import Destinations, Event
from audio_platform.modules.processing.domain import (
    SAMPLE_RATE,
    InvalidAudio,
    ProcessingJob,
    StageName,
    VadParameters,
    VadResult,
    speech_segments,
)
from audio_platform.modules.processing.ports import (
    ArtifactStorage,
    AudioAnalyzer,
    ProcessingUnitOfWorkFactory,
)
from audio_platform.modules.processing.services.coordinator import EventTypes

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def artifact_key(object_key: str, name: str) -> str:
    """Artifacts sit next to the original: users/<owner>/recordings/<id>/<name>."""
    return f"{object_key.rsplit('/', 1)[0]}/{name}"


@dataclass(frozen=True, slots=True)
class VadWorkerConfig:
    params: VadParameters
    max_duration_s: int
    max_attempts: int


class VadWorker:
    """
    Validates, normalizes and runs VAD for one job. Storage and CPU work happen
    outside any transaction; status changes and the outgoing event are committed
    together, so the coordinator hears about every outcome exactly as recorded.
    """

    def __init__(
        self,
        uow: ProcessingUnitOfWorkFactory,
        storage: ArtifactStorage,
        analyzer: AudioAnalyzer,
        config: VadWorkerConfig,
        *,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._uow = uow
        self._storage = storage
        self._analyzer = analyzer
        self._config = config
        self._clock = clock

    async def handle(self, data: dict[str, Any], *, receive_count: int) -> None:
        job = await self._claim(UUID(data["job_id"]))
        if job is None:
            return
        logger.info(LogEvent.VAD_STARTED, job_id=str(job.id), attempt=receive_count)
        try:
            summary = await self._process(job)
        except InvalidAudio as exc:
            await self._finish_failed(job.id, f"invalid audio: {exc}")
            return
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            if receive_count >= self._config.max_attempts:
                await self._finish_failed(
                    job.id, f"gave up after {receive_count} attempts ({error})"
                )
                return
            await self._record_retryable_error(job.id, error)
            logger.warning(
                LogEvent.VAD_RETRY_SCHEDULED, job_id=str(job.id), attempt=receive_count
            )
            raise  # the message stays in the queue and is redelivered
        await self._finish_succeeded(job.id, summary)

    async def _claim(self, job_id: UUID) -> ProcessingJob | None:
        async with self._uow() as uow:
            job = await uow.jobs.get(job_id, for_update=True)
            if job is None or job.is_finished or job.stage(StageName.VAD).is_finished:
                return None  # a redelivered task whose work is already recorded
            job.begin_stage(StageName.VAD, now=self._clock())
            await uow.jobs.update(job)
            await uow.commit()
        return job

    async def _process(self, job: ProcessingJob) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="vad-") as tmp:
            original, normalized = Path(tmp) / "original", Path(tmp) / "normalized.wav"
            await self._storage.download(job.object_key, original)

            analysis = await self._analyzer.analyze(
                original, normalized, max_duration_s=self._config.max_duration_s
            )
            info, samples = analysis.info, analysis.samples
            result = VadResult(
                duration_ms=samples * 1000 // SAMPLE_RATE,
                segments=speech_segments(
                    analysis.probabilities, samples, self._config.params
                ),
            )

            normalized_key = artifact_key(job.object_key, "normalized.wav")
            segments_key = artifact_key(job.object_key, "vad.json")
            await self._storage.upload_file(
                normalized_key, normalized, content_type="audio/wav"
            )
            await self._storage.put_json(segments_key, self._segments_document(result))

        return {
            "speech_detected": result.speech_detected,
            "duration_ms": result.duration_ms,
            "speech_ms": result.speech_ms,
            "speech_ratio": result.speech_ratio,
            "segment_count": len(result.segments),
            "normalized_key": normalized_key,
            "segments_key": segments_key,
            "source": {
                "container": info.container,
                "codec": info.codec,
                "sample_rate": info.sample_rate,
                "channels": info.channels,
            },
        }

    def _segments_document(self, result: VadResult) -> dict[str, Any]:
        params = self._config.params
        return {
            "version": 1,
            "sample_rate": SAMPLE_RATE,
            "duration_ms": result.duration_ms,
            "parameters": {
                "threshold": params.threshold,
                "min_speech_ms": params.min_speech_ms,
                "min_silence_ms": params.min_silence_ms,
                "speech_pad_ms": params.speech_pad_ms,
            },
            "segments": [
                {"start_ms": s.start_ms, "end_ms": s.end_ms} for s in result.segments
            ],
        }

    async def _finish_succeeded(self, job_id: UUID, summary: dict[str, Any]) -> None:
        async with self._uow() as uow:
            job = await uow.jobs.get(job_id, for_update=True)
            if job is None or job.is_finished or job.stage(StageName.VAD).is_finished:
                return
            job.succeed_stage(StageName.VAD, summary, now=self._clock())
            await uow.jobs.update(job)
            await uow.outbox.add(
                Event.new(
                    EventTypes.VAD_COMPLETED,
                    {
                        "job_id": str(job_id),
                        "speech_detected": summary["speech_detected"],
                    },
                ),
                destination=Destinations.PIPELINE_EVENTS,
            )
            await uow.commit()
        logger.info(
            LogEvent.VAD_COMPLETED,
            job_id=str(job_id),
            speech_detected=summary["speech_detected"],
            segment_count=summary["segment_count"],
        )

    async def _finish_failed(self, job_id: UUID, error: str) -> None:
        async with self._uow() as uow:
            job = await uow.jobs.get(job_id, for_update=True)
            if job is None or job.is_finished or job.stage(StageName.VAD).is_finished:
                return
            job.fail_stage(StageName.VAD, error, now=self._clock())
            await uow.jobs.update(job)
            await uow.outbox.add(
                Event.new(
                    EventTypes.VAD_FAILED, {"job_id": str(job_id), "error": error}
                ),
                destination=Destinations.PIPELINE_EVENTS,
            )
            await uow.commit()
        logger.warning(LogEvent.VAD_FAILED, job_id=str(job_id), error=error)

    async def _record_retryable_error(self, job_id: UUID, error: str) -> None:
        async with self._uow() as uow:
            job = await uow.jobs.get(job_id, for_update=True)
            if job is None or job.is_finished or job.stage(StageName.VAD).is_finished:
                return
            job.record_retryable_error(StageName.VAD, error, now=self._clock())
            await uow.jobs.update(job)
            await uow.commit()
