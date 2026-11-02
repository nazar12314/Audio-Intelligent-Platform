from dataclasses import dataclass
from typing import Any
from uuid import UUID

from audio_platform.core.exceptions import NotFoundError
from audio_platform.modules.processing.domain import (
    ProcessingJob,
    SpeechSegment,
    StageName,
    StageStatus,
    Transcript,
    TranscriptSegment,
)
from audio_platform.modules.processing.ports import (
    ArtifactStorage,
    ProcessingUnitOfWorkFactory,
)


@dataclass(frozen=True, slots=True)
class ProcessingView:
    job: ProcessingJob
    segments: list[SpeechSegment] | None  # None until VAD has succeeded
    transcript: Transcript | None = None  # None until ASR has succeeded


class ProcessingQueries:
    def __init__(
        self, uow: ProcessingUnitOfWorkFactory, storage: ArtifactStorage
    ) -> None:
        self._uow = uow
        self._storage = storage

    async def for_recording(self, owner_id: UUID, recording_id: UUID) -> ProcessingView:
        async with self._uow() as uow:
            job = await uow.jobs.get_for_owner(recording_id, owner_id)

        if job is None:
            raise NotFoundError("processing job for recording", recording_id)

        segments = None
        document = await self._artifact(job, StageName.VAD, "segments_key")
        if document is not None:
            segments = [
                SpeechSegment(s["start_ms"], s["end_ms"]) for s in document["segments"]
            ]

        transcript = None
        document = await self._artifact(job, StageName.ASR, "transcript_key")
        if document is not None:
            transcript = Transcript(
                language=document["language"],
                language_probability=document["language_probability"],
                segments=[
                    TranscriptSegment(s["start_ms"], s["end_ms"], s["text"])
                    for s in document["segments"]
                ],
            )
        return ProcessingView(job=job, segments=segments, transcript=transcript)

    async def _artifact(
        self, job: ProcessingJob, stage_name: StageName, key: str
    ) -> dict[str, Any] | None:
        stage = job.stages.get(stage_name)
        if stage is None or stage.status is not StageStatus.SUCCEEDED:
            return None
        if stage.result is None:
            return None
        document: dict[str, Any] | None = await self._storage.get_json(
            stage.result[key]
        )
        return document
