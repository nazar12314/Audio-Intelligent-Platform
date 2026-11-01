from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class JobStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StageName(StrEnum):
    VAD = "vad"  # validate, normalize to 16 kHz mono, detect speech


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"  # also while a failed attempt waits for its retry
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class InvalidJobTransition(Exception):
    pass


@dataclass(slots=True)
class Stage:
    name: StageName
    status: StageStatus = StageStatus.PENDING
    attempts: int = 0
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: dict[str, Any] | None = None

    @property
    def is_finished(self) -> bool:
        return self.status in (StageStatus.SUCCEEDED, StageStatus.FAILED)


@dataclass(slots=True)
class ProcessingJob:
    id: UUID
    recording_id: UUID
    owner_id: UUID
    object_key: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    stages: dict[StageName, Stage] = field(default_factory=dict)
    speech_detected: bool | None = None
    failure_reason: str | None = None
    completed_at: datetime | None = None

    @classmethod
    def start(
        cls,
        *,
        job_id: UUID,
        recording_id: UUID,
        owner_id: UUID,
        object_key: str,
        now: datetime,
    ) -> ProcessingJob:
        return cls(
            id=job_id,
            recording_id=recording_id,
            owner_id=owner_id,
            object_key=object_key,
            status=JobStatus.RUNNING,
            created_at=now,
            updated_at=now,
            stages={StageName.VAD: Stage(StageName.VAD)},
        )

    @property
    def is_finished(self) -> bool:
        return self.status is not JobStatus.RUNNING

    def stage(self, name: StageName) -> Stage:
        return self.stages[name]

    def begin_stage(self, name: StageName, *, now: datetime) -> None:
        stage = self._open_stage(name)
        stage.status = StageStatus.RUNNING
        stage.attempts += 1
        stage.started_at = stage.started_at or now
        self.updated_at = now

    def record_retryable_error(
        self, name: StageName, error: str, *, now: datetime
    ) -> None:
        self._open_stage(name).error = error
        self.updated_at = now

    def succeed_stage(
        self, name: StageName, result: dict[str, Any], *, now: datetime
    ) -> None:
        stage = self._open_stage(name)
        stage.status, stage.result, stage.error = StageStatus.SUCCEEDED, result, None
        stage.finished_at = self.updated_at = now

    def fail_stage(self, name: StageName, error: str, *, now: datetime) -> None:
        stage = self._open_stage(name)
        stage.status, stage.error = StageStatus.FAILED, error
        stage.finished_at = self.updated_at = now

    def complete(self, *, speech_detected: bool, now: datetime) -> None:
        self._require_running()
        self.status, self.speech_detected = JobStatus.COMPLETED, speech_detected
        self.completed_at = self.updated_at = now

    def fail(self, reason: str, *, now: datetime) -> None:
        self._require_running()
        self.status, self.failure_reason = JobStatus.FAILED, reason
        self.completed_at = self.updated_at = now

    def _open_stage(self, name: StageName) -> Stage:
        self._require_running()
        stage = self.stages[name]
        if stage.is_finished:
            raise InvalidJobTransition(f"stage {name} is already {stage.status}")
        return stage

    def _require_running(self) -> None:
        if self.is_finished:
            raise InvalidJobTransition(f"job is already {self.status}")
