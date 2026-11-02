import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from audio_platform.modules.processing.domain import (
    ProcessingJob,
    SpeechSegment,
    StageName,
    Transcript,
)
from audio_platform.modules.processing.ports import (
    ArtifactStorage,
    ProcessingUnitOfWorkFactory,
    SpeechTranscriber,
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
class AsrWorkerConfig:
    model: str  # recorded with every transcript
    max_attempts: int


class AsrWorker:
    """
    Transcribes the speech VAD found, reading the normalized audio and segments VAD
    stored. Stores `transcript.json` (segments and text, what the API serves) and
    `words.json` (word timings, for later stages) next to them.
    """

    def __init__(
        self,
        uow: ProcessingUnitOfWorkFactory,
        storage: ArtifactStorage,
        transcriber: SpeechTranscriber,
        config: AsrWorkerConfig,
        *,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._storage = storage
        self._transcriber = transcriber
        self._config = config
        self._task = StageTask(
            uow,
            StageName.ASR,
            completed_event=EventTypes.ASR_COMPLETED,
            failed_event=EventTypes.ASR_FAILED,
            max_attempts=config.max_attempts,
            clock=clock,
        )

    async def handle(self, data: dict[str, Any], *, receive_count: int) -> None:
        await self._task.run(data, receive_count=receive_count, work=self._process)

    async def _process(self, job: ProcessingJob) -> StageOutcome:
        vad = job.stage(StageName.VAD).result
        if vad is None:
            raise LookupError("VAD result is missing")

        document = await self._storage.get_json(vad["segments_key"])
        if document is None:
            raise LookupError(f"{vad['segments_key']} is missing")
        speech = [
            SpeechSegment(s["start_ms"], s["end_ms"]) for s in document["segments"]
        ]

        with tempfile.TemporaryDirectory(prefix="asr-") as tmp:
            wav = Path(tmp) / "normalized.wav"
            await self._storage.download(vad["normalized_key"], wav)
            transcript = await self._transcriber.transcribe(wav, speech)

        transcript_key = artifact_key(job.object_key, "transcript.json")
        words_key = artifact_key(job.object_key, "words.json")
        await self._storage.put_json(transcript_key, self._transcript(transcript))
        await self._storage.put_json(words_key, self._words(transcript))

        return StageOutcome(
            result={
                "language": transcript.language,
                "language_probability": round(transcript.language_probability, 4),
                "segment_count": len(transcript.segments),
                "model": self._config.model,
                "transcript_key": transcript_key,
                "words_key": words_key,
            },
            event_data={"language": transcript.language},
        )

    def _transcript(self, transcript: Transcript) -> dict[str, Any]:
        return {
            "version": 3,
            "model": self._config.model,
            "language": transcript.language,
            "language_probability": round(transcript.language_probability, 4),
            "text": transcript.text,
            "segments": [
                {"start_ms": s.start_ms, "end_ms": s.end_ms, "text": s.text}
                for s in transcript.segments
            ],
        }

    def _words(self, transcript: Transcript) -> dict[str, Any]:
        """Word timings per transcript segment, in the same order."""
        return {
            "version": 1,
            "model": self._config.model,
            "segments": [
                [
                    {
                        "start_ms": w.start_ms,
                        "end_ms": w.end_ms,
                        "text": w.text,
                        "probability": round(w.probability, 4),
                    }
                    for w in s.words
                ]
                for s in transcript.segments
            ],
        }
