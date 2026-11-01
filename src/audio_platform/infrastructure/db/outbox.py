import asyncio
import contextlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy import DateTime, Index, String, Uuid, delete, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from audio_platform.core.logging import LogEvent, get_logger
from audio_platform.core.messaging import Event, EventPublisher, UnknownDestination
from audio_platform.infrastructure.db.base import Base

logger = get_logger(__name__)


class OutboxRow(Base):
    __tablename__ = "outbox"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)  # the event ID
    destination: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "ix_outbox_pending",
            "created_at",
            postgresql_where=published_at.is_(None),
        ),
    )


class SqlOutbox:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: Event, *, destination: str) -> None:
        self._session.add(
            OutboxRow(
                id=event.id,
                destination=destination,
                payload=event.model_dump(mode="json"),
                created_at=event.occurred_at,
            )
        )


class OutboxRelay:
    """
    Publishes committed outbox rows. Delivery is at-least-once: a crash between
    publishing and marking a row republishes it, so consumers must be idempotent.
    """

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        publisher: EventPublisher,
        *,
        batch_size: int,
        interval_s: float,
    ) -> None:
        self._sessions = sessions
        self._publisher = publisher
        self._batch_size = batch_size
        self._interval_s = interval_s

    async def publish_pending(self) -> int:
        async with self._sessions() as session, session.begin():
            rows = (
                (
                    await session.execute(
                        select(OutboxRow)
                        .where(OutboxRow.published_at.is_(None))
                        .order_by(OutboxRow.created_at)
                        .limit(self._batch_size)
                        .with_for_update(skip_locked=True)  # parallel relays split work
                    )
                )
                .scalars()
                .all()
            )
            for row in rows:
                try:
                    event = Event.model_validate(row.payload)
                    await self._publisher.publish(event, destination=row.destination)
                except (ValidationError, UnknownDestination) as exc:
                    # A row that can never be published must not block the rows
                    # behind it; it stays pending and visible in the logs.
                    logger.error(
                        LogEvent.OUTBOX_ROW_UNPUBLISHABLE,
                        outbox_id=str(row.id),
                        error=type(exc).__name__,
                    )
                    continue
                row.published_at = datetime.now(UTC)
        return len(rows)

    async def run(self, stop: asyncio.Event) -> None:
        failures = 0
        while not stop.is_set():
            try:
                published = await self.publish_pending()
                failures = 0
            except Exception:
                failures += 1
                logger.exception(LogEvent.OUTBOX_RELAY_FAILED, failures=failures)
                published = 0
            if published < self._batch_size:
                delay = self._interval_s * min(2**failures, 30)
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=delay)


class OutboxCleaner:
    """
    Deletes rows published longer ago than the retention period. Small batches with
    SKIP LOCKED keep transactions short and let several pipeline processes share it.
    """

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        retention: timedelta,
        interval_s: float,
        batch_size: int = 1000,
    ) -> None:
        self._sessions = sessions
        self._retention = retention
        self._interval_s = interval_s
        self._batch_size = batch_size

    async def purge(self) -> int:
        cutoff = datetime.now(UTC) - self._retention
        total = 0
        while True:
            async with self._sessions() as session, session.begin():
                batch = (
                    select(OutboxRow.id)
                    .where(OutboxRow.published_at < cutoff)
                    .limit(self._batch_size)
                    .with_for_update(skip_locked=True)
                    .scalar_subquery()
                )
                result = await session.execute(
                    delete(OutboxRow).where(OutboxRow.id.in_(batch))
                )
            deleted = result.rowcount or 0  # type: ignore[attr-defined]
            total += deleted
            if deleted < self._batch_size:
                return total

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                if deleted := await self.purge():
                    logger.info(LogEvent.OUTBOX_PURGED, rows=deleted)
            except Exception:
                logger.exception(LogEvent.OUTBOX_CLEANUP_FAILED)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self._interval_s)
