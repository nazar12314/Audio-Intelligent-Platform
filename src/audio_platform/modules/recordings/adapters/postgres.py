import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from types import TracebackType
from typing import Self

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    String,
    Text,
    Uuid,
    select,
    update,
)
from sqlalchemy.exc import (
    IntegrityError,
    InterfaceError,
    OperationalError,
)
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from audio_platform.core.exceptions import ConflictError, DependencyUnavailable
from audio_platform.infrastructure.db import TimestampedModel
from audio_platform.infrastructure.db.outbox import SqlOutbox
from audio_platform.modules.recordings.domain import Recording, RecordingStatus

_STATUSES = ", ".join(f"'{s.value}'" for s in RecordingStatus)


class RecordingRow(TimestampedModel):
    __tablename__ = "recordings"

    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    part_size_bytes: Mapped[int] = mapped_column(BigInteger)
    object_key: Mapped[str] = mapped_column(String(512), unique=True)
    status: Mapped[str] = mapped_column(String(32))
    upload_id: Mapped[str | None] = mapped_column(Text)
    etag: Mapped[str | None] = mapped_column(String(128))
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(f"status IN ({_STATUSES})", name="status"),
        CheckConstraint("size_bytes > 0", name="size_positive"),
        CheckConstraint("part_size_bytes > 0", name="part_size_positive"),
        Index("ix_recordings_owner_id_id", "owner_id", "id"),
    )


def _to_row_values(recording: Recording) -> dict[str, object]:
    return {
        "id": recording.id,
        "owner_id": recording.owner_id,
        "filename": recording.filename,
        "content_type": recording.content_type,
        "size_bytes": recording.size_bytes,
        "part_size_bytes": recording.part_size_bytes,
        "object_key": recording.object_key,
        "status": recording.status.value,
        "upload_id": recording.upload_id,
        "etag": recording.etag,
        "uploaded_at": recording.uploaded_at,
        "failure_reason": recording.failure_reason,
        "created_at": recording.created_at,
        "updated_at": recording.updated_at,
    }


def _to_domain(row: RecordingRow) -> Recording:
    return Recording(
        id=row.id,
        owner_id=row.owner_id,
        filename=row.filename,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        part_size_bytes=row.part_size_bytes,
        object_key=row.object_key,
        status=RecordingStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
        upload_id=row.upload_id,
        etag=row.etag,
        uploaded_at=row.uploaded_at,
        failure_reason=row.failure_reason,
    )


@contextmanager
def _translate_errors() -> Iterator[None]:
    try:
        yield
    except IntegrityError:
        raise ConflictError("recording conflicts with an existing one") from None
    # PoolTimeout (pool exhausted) is SQLAlchemy's own, unrelated to TimeoutError.
    except OperationalError, InterfaceError, PoolTimeout, OSError, TimeoutError:
        raise DependencyUnavailable("database unavailable") from None


class PostgresRecordingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, recording: Recording) -> None:
        with _translate_errors():
            self._session.add(RecordingRow(**_to_row_values(recording)))
            await self._session.flush()

    async def get_for_owner(
        self, recording_id: uuid.UUID, owner_id: uuid.UUID, *, for_update: bool = False
    ) -> Recording | None:
        query = select(RecordingRow).where(
            RecordingRow.id == recording_id, RecordingRow.owner_id == owner_id
        )
        if for_update:
            query = query.with_for_update()
        with _translate_errors():
            row = (await self._session.execute(query)).scalar_one_or_none()
        return None if row is None else _to_domain(row)

    async def list_for_owner(
        self, owner_id: uuid.UUID, *, limit: int, before_id: uuid.UUID | None = None
    ) -> list[Recording]:
        query = (
            select(RecordingRow)
            .where(RecordingRow.owner_id == owner_id)
            .order_by(RecordingRow.id.desc())
            .limit(limit)
        )
        if before_id is not None:
            query = query.where(RecordingRow.id < before_id)
        with _translate_errors():
            rows = (await self._session.execute(query)).scalars().all()
        return [_to_domain(row) for row in rows]

    async def update(self, recording: Recording) -> None:
        values = _to_row_values(recording)
        del values["id"], values["owner_id"], values["created_at"]
        with _translate_errors():
            await self._session.execute(
                update(RecordingRow)
                .where(
                    RecordingRow.id == recording.id,
                    RecordingRow.owner_id == recording.owner_id,
                )
                .values(**values)
                .execution_options(synchronize_session=False)
            )


class SqlRecordingUnitOfWork:
    recordings: PostgresRecordingRepository
    outbox: SqlOutbox
    _session: AsyncSession

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def __aenter__(self) -> Self:
        self._session = self._sessions()
        self.recordings = PostgresRecordingRepository(self._session)
        self.outbox = SqlOutbox(self._session)
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
