import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from audio_platform.modules.processing.domain import (
    SAMPLE_RATE,
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
from audio_platform.modules.processing.services.stage_task import (
    StageOutcome,
    StageTask,
    artifact_key,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class VadWorkerConfig:
    params: VadParameters
    max_duration_s: int
    max_attempts: int


class VadWorker:
    """Validates, normalizes and runs VAD for one job."""

    def __init__(
        self,
        uow: ProcessingUnitOfWorkFactory,
        storage: ArtifactStorage,
        analyzer: AudioAnalyzer,
        config: VadWorkerConfig,
        *,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._storage = storage
        self._analyzer = analyzer
        self._config = config
        self._task = StageTask(
            uow,
            StageName.VAD,
            completed_event=EventTypes.VAD_COMPLETED,
            failed_event=EventTypes.VAD_FAILED,
            max_attempts=config.max_attempts,
            clock=clock,
        )

    async def handle(self, data: dict[str, Any], *, receive_count: int) -> None:
        await self._task.run(data, receive_count=receive_count, work=self._process)

    async def _process(self, job: ProcessingJob) -> StageOutcome:
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

        return StageOutcome(
            result={
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
            },
            event_data={"speech_detected": result.speech_detected},
        )

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
