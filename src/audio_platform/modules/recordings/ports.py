"""Interfaces the recordings feature depends on. Implementations live in adapters/."""

from collections.abc import Callable, Sequence
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from audio_platform.modules.recordings.domain import (
    Recording,
    StoredObject,
    UploadedPart,
)


class RecordingRepository(Protocol):
    """
    System of record for recording metadata. Ownership is enforced inside the
    queries.
    """

    async def add(self, recording: Recording) -> None: ...

    async def get_for_owner(
        self, recording_id: UUID, owner_id: UUID, *, for_update: bool = False
    ) -> Recording | None: ...

    async def update(self, recording: Recording) -> None: ...

    async def list_for_owner(
        self, owner_id: UUID, *, limit: int, before_id: UUID | None = None
    ) -> list[Recording]:
        """Newest first (IDs are UUIDv7, so ID order is creation order)."""
        ...


class RecordingUnitOfWork(Protocol):
    @property
    def recordings(self) -> RecordingRepository: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


UnitOfWorkFactory = Callable[[], RecordingUnitOfWork]


class UploadNotFound(Exception):
    """The multipart upload no longer exists (completed, aborted or expired)."""


class PartsRejected(Exception):
    """Storage refused the part list (unknown part, wrong ETag, part too small)."""


class AudioObjectStorage(Protocol):
    """
    Object storage for audio files. The client uploads parts directly via
    presigned URLs.
    """

    async def create_multipart_upload(self, key: str, content_type: str) -> str:
        """Start a multipart upload and return its upload ID."""
        ...

    async def presign_upload_part(
        self,
        key: str,
        upload_id: str,
        part_number: int,
        expires_in_s: int,
        *,
        content_length: int,
    ) -> str:
        """
        The URL is signed for exactly `content_length` bytes: storage rejects any
        other body size when the part is uploaded.
        """
        ...

    async def complete_multipart_upload(
        self, key: str, upload_id: str, parts: Sequence[UploadedPart]
    ) -> None: ...

    async def abort_multipart_upload(self, key: str, upload_id: str) -> None: ...

    async def presign_download(self, key: str, expires_in_s: int) -> str: ...

    async def head_object(self, key: str) -> StoredObject | None:
        """Return the committed object's metadata, or None if it does not exist."""
        ...

    async def delete_object(self, key: str, *, version_id: str | None = None) -> None:
        """
        Delete the object; with a version ID, that version is removed permanently
        instead of leaving it behind a delete marker. Missing objects are not an error.
        """
        ...
