import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from types import TracebackType
from typing import Any, Self

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    delete,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from audio_platform.core.exceptions import ConflictError, DependencyUnavailable
from audio_platform.infrastructure.db import TimestampedModel
from audio_platform.infrastructure.db.base import Base
from audio_platform.infrastructure.db.outbox import SqlOutbox
from audio_platform.modules.processing.domain import (
    JobStatus,
    ProcessingJob,
    Stage,
    StageName,
    StageStatus,
)


def _values(enum: type[JobStatus] | type[StageStatus] | type[StageName]) -> str:
    return ", ".join(f"'{member.value}'" for member in enum)


class ProcessingJobRow(TimestampedModel):
    __tablename__ = "processing_jobs"

    recording_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    object_key: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32))
    speech_detected: Mapped[bool | None]
    failure_reason: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(f"status IN ({_values(JobStatus)})", name="status"),
    )


class ProcessingStageRow(Base):
    __tablename__ = "processing_stages"

    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("processing_jobs.id", ondelete="CASCADE"), primary_key=True
    )
    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(32))
    attempts: Mapped[int] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (
        CheckConstraint(f"name IN ({_values(StageName)})", name="name"),
        CheckConstraint(f"status IN ({_values(StageStatus)})", name="status"),
    )


def _to_domain(
    row: ProcessingJobRow, stages: list[ProcessingStageRow]
) -> ProcessingJob:
    return ProcessingJob(
        id=row.id,
        recording_id=row.recording_id,
        owner_id=row.owner_id,
        object_key=row.object_key,
        status=JobStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
        speech_detected=row.speech_detected,
        failure_reason=row.failure_reason,
        completed_at=row.completed_at,
        stages={
            StageName(s.name): Stage(
                name=StageName(s.name),
                status=StageStatus(s.status),
                attempts=s.attempts,
                error=s.error,
                started_at=s.started_at,
                finished_at=s.finished_at,
                result=s.result,
            )
            for s in stages
        },
    )


def _stage_rows(job: ProcessingJob) -> list[ProcessingStageRow]:
    return [
        ProcessingStageRow(
            job_id=job.id,
            name=stage.name.value,
            status=stage.status.value,
            attempts=stage.attempts,
            error=stage.error,
            started_at=stage.started_at,
            finished_at=stage.finished_at,
            result=stage.result,
        )
        for stage in job.stages.values()
    ]


@contextmanager
def _translate_errors() -> Iterator[None]:
    try:
        yield
    except IntegrityError:
        raise ConflictError("processing job conflicts with an existing one") from None
    except OperationalError, InterfaceError, PoolTimeout, OSError, TimeoutError:
        raise DependencyUnavailable("database unavailable") from None


class PostgresProcessingJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, job: ProcessingJob) -> None:
        with _translate_errors():
            self._session.add(
                ProcessingJobRow(
                    id=job.id,
                    recording_id=job.recording_id,
                    owner_id=job.owner_id,
                    object_key=job.object_key,
                    status=job.status.value,
                    speech_detected=job.speech_detected,
                    failure_reason=job.failure_reason,
                    completed_at=job.completed_at,
                    created_at=job.created_at,
                    updated_at=job.updated_at,
                )
            )
            await self._session.flush()
            self._session.add_all(_stage_rows(job))
            await self._session.flush()

    async def get(
        self, job_id: uuid.UUID, *, for_update: bool = False
    ) -> ProcessingJob | None:
        query = select(ProcessingJobRow).where(ProcessingJobRow.id == job_id)
        return await self._load(query.with_for_update() if for_update else query)

    async def find_by_recording(self, recording_id: uuid.UUID) -> ProcessingJob | None:
        return await self._load(
            select(ProcessingJobRow).where(
                ProcessingJobRow.recording_id == recording_id
            )
        )

    async def get_for_owner(
        self, recording_id: uuid.UUID, owner_id: uuid.UUID
    ) -> ProcessingJob | None:
        return await self._load(
            select(ProcessingJobRow).where(
                ProcessingJobRow.recording_id == recording_id,
                ProcessingJobRow.owner_id == owner_id,
            )
        )

    async def update(self, job: ProcessingJob) -> None:
        with _translate_errors():
            row = await self._session.get(ProcessingJobRow, job.id)
            if row is None:
                return
            row.status = job.status.value
            row.speech_detected = job.speech_detected
            row.failure_reason = job.failure_reason
            row.completed_at = job.completed_at
            row.updated_at = job.updated_at
            await self._session.execute(
                delete(ProcessingStageRow).where(ProcessingStageRow.job_id == job.id)
            )
            self._session.add_all(_stage_rows(job))
            await self._session.flush()

    async def _load(self, query: Any) -> ProcessingJob | None:
        with _translate_errors():
            row = (await self._session.execute(query)).scalar_one_or_none()
            if row is None:
                return None
            stages = (
                (
                    await self._session.execute(
                        select(ProcessingStageRow).where(
                            ProcessingStageRow.job_id == row.id
                        )
                    )
                )
                .scalars()
                .all()
            )
        return _to_domain(row, list(stages))


class SqlProcessingUnitOfWork:
    _session: AsyncSession
    _jobs: PostgresProcessingJobRepository
    _outbox: SqlOutbox

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    @property
    def jobs(self) -> PostgresProcessingJobRepository:
        return self._jobs

    @property
    def outbox(self) -> SqlOutbox:
        return self._outbox

    async def __aenter__(self) -> Self:
        self._session = self._sessions()
        self._jobs = PostgresProcessingJobRepository(self._session)
        self._outbox = SqlOutbox(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            await self._session.rollback()  # no-op after a successful commit
        finally:
            await self._session.close()

    async def commit(self) -> None:
        with _translate_errors():
            await self._session.commit()
