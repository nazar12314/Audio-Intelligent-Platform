import uuid
from datetime import UTC, datetime
from typing import Any, Protocol

import structlog
from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Event(BaseModel):
    """Envelope shared by every message. Consumers deduplicate on `id`."""

    id: uuid.UUID = Field(default_factory=uuid.uuid7)
    type: str  # <feature>.<entity>.<past_tense_verb>, or a command: ....requested
    version: int = 1
    occurred_at: datetime = Field(default_factory=_utcnow)
    correlation_id: str | None = None
    data: dict[str, Any]

    @classmethod
    def new(cls, type: str, data: dict[str, Any]) -> Event:
        return cls(type=type, data=data, correlation_id=current_correlation_id())


def current_correlation_id() -> str | None:
    value = structlog.contextvars.get_contextvars().get("request_id")
    return str(value) if value else None


class UnknownDestination(LookupError):
    pass


class EventPublisher(Protocol):
    async def publish(self, event: Event, *, destination: str) -> None:
        """Raise UnknownDestination when no queue is mapped to `destination`."""
        ...


class Outbox(Protocol):
    """Stores events in the caller's transaction; a relay publishes them later."""

    async def add(self, event: Event, *, destination: str) -> None: ...


class Destinations:
    """Logical message destinations; adapters map them to queues."""

    PIPELINE_EVENTS = "pipeline-events"
    VAD_TASKS = "vad-tasks"
