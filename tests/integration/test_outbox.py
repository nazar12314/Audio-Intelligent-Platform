from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from audio_platform.core.config import Settings
from audio_platform.core.messaging import Event, UnknownDestination
from audio_platform.infrastructure.db import session_factory, sql_engine
from audio_platform.infrastructure.db.outbox import (
    OutboxCleaner,
    OutboxRelay,
    OutboxRow,
)

pytestmark = pytest.mark.integration


class RecordingPublisher:
    def __init__(self) -> None:
        self.published: list[tuple[str, Event]] = []

    async def publish(self, event: Event, *, destination: str) -> None:
        if destination != "pipeline-events":
            raise UnknownDestination(destination)
        self.published.append((destination, event))


@pytest.fixture
async def sessions(
    settings: Settings,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    async with sql_engine(settings.postgres, application_name="tests") as engine:
        sessions = session_factory(engine)
        yield sessions
        async with sessions() as session, session.begin():
            await session.execute(
                delete(OutboxRow).where(OutboxRow.destination.like("test-%"))
            )


def _row(
    destination: str,
    *,
    published_at: datetime | None,
    payload: dict[str, object] | None = None,
) -> OutboxRow:
    event = Event.new("test.outbox.row", {})
    return OutboxRow(
        id=event.id,
        destination=destination,
        payload=payload if payload is not None else event.model_dump(mode="json"),
        created_at=datetime.now(UTC) - timedelta(days=9),
        published_at=published_at,
    )


async def test_cleanup_deletes_only_rows_published_before_the_cutoff(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(UTC)
    rows = {
        "old_published": _row("test-cleanup", published_at=now - timedelta(days=8)),
        "recent_published": _row("test-cleanup", published_at=now - timedelta(days=1)),
        "old_pending": _row("test-cleanup", published_at=None),
    }
    ids = {name: row.id for name, row in rows.items()}
    async with sessions() as session, session.begin():
        session.add_all(rows.values())

    cleaner = OutboxCleaner(
        sessions, retention=timedelta(days=7), interval_s=3600, batch_size=1
    )
    deleted = await cleaner.purge()

    async with sessions() as session:
        remaining = set(
            (
                await session.execute(
                    select(OutboxRow.id).where(OutboxRow.id.in_(ids.values()))
                )
            ).scalars()
        )
    assert deleted >= 1
    assert remaining == {ids["recent_published"], ids["old_pending"]}


async def test_unpublishable_rows_do_not_block_the_relay(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    good = _row("pipeline-events", published_at=None)
    corrupt = _row("test-relay", published_at=None, payload={"not": "an event"})
    unroutable = _row("test-relay", published_at=None)
    good.created_at = datetime.now(UTC)  # newest, so it sorts behind the bad rows
    async with sessions() as session, session.begin():
        session.add_all([corrupt, unroutable, good])
    publisher = RecordingPublisher()

    await OutboxRelay(
        sessions, publisher, batch_size=500, interval_s=1
    ).publish_pending()

    assert good.id in {event.id for _, event in publisher.published}
    async with sessions() as session:
        result = await session.execute(
            select(OutboxRow.id, OutboxRow.published_at).where(
                OutboxRow.id.in_([good.id, corrupt.id, unroutable.id])
            )
        )
        states = dict(result.all())
        await session.execute(delete(OutboxRow).where(OutboxRow.id == good.id))
        await session.commit()
    assert states[good.id] is not None
    assert states[corrupt.id] is None and states[unroutable.id] is None
