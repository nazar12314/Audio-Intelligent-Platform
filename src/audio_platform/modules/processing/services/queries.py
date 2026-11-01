from dataclasses import dataclass
from typing import Any
from uuid import UUID

from audio_platform.core.exceptions import NotFoundError
from audio_platform.modules.processing.domain import (
    ProcessingJob,
    SpeechSegment,
    StageName,
    StageStatus,
)
from audio_platform.modules.processing.ports import (
    ArtifactStorage,
    ProcessingUnitOfWorkFactory,
)


@dataclass(frozen=True, slots=True)
class ProcessingView:
    job: ProcessingJob
    segments: list[SpeechSegment] | None  # None until VAD has succeeded


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

        vad = job.stage(StageName.VAD)
        segments = None

        if vad.status is StageStatus.SUCCEEDED and vad.result:
            document: dict[str, Any] | None = await self._storage.get_json(
                vad.result["segments_key"]
            )
            if document is not None:
                segments = [
                    SpeechSegment(s["start_ms"], s["end_ms"])
                    for s in document["segments"]
                ]
        return ProcessingView(job=job, segments=segments)
