from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from audio_platform.modules.processing.domain import (
    JobStatus,
    SpeechSegment,
    StageName,
    StageStatus,
)
from audio_platform.modules.processing.services import ProcessingView


class StageOut(BaseModel):
    name: StageName
    status: StageStatus
    attempts: int
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None


class SegmentOut(BaseModel):
    start_ms: int
    end_ms: int


class VadOut(BaseModel):
    speech_detected: bool
    duration_ms: int
    speech_ms: int
    speech_ratio: float
    segments: list[SegmentOut]


class ProcessingOut(BaseModel):
    job_id: UUID
    recording_id: UUID
    status: JobStatus
    speech_detected: bool | None
    failure_reason: str | None
    created_at: datetime
    completed_at: datetime | None
    stages: list[StageOut]
    vad: VadOut | None

    @classmethod
    def from_view(cls, view: ProcessingView) -> ProcessingOut:
        job = view.job
        vad_result = job.stage(StageName.VAD).result
        vad = None
        if vad_result is not None and view.segments is not None:
            vad = VadOut(
                speech_detected=vad_result["speech_detected"],
                duration_ms=vad_result["duration_ms"],
                speech_ms=vad_result["speech_ms"],
                speech_ratio=vad_result["speech_ratio"],
                segments=[_segment(s) for s in view.segments],
            )
        return cls(
            job_id=job.id,
            recording_id=job.recording_id,
            status=job.status,
            speech_detected=job.speech_detected,
            failure_reason=job.failure_reason,
            created_at=job.created_at,
            completed_at=job.completed_at,
            stages=[
                StageOut(
                    name=s.name,
                    status=s.status,
                    attempts=s.attempts,
                    error=s.error,
                    started_at=s.started_at,
                    finished_at=s.finished_at,
                )
                for s in job.stages.values()
            ],
            vad=vad,
        )


def _segment(segment: SpeechSegment) -> SegmentOut:
    return SegmentOut(start_ms=segment.start_ms, end_ms=segment.end_ms)
