"""Interfaces the recordings feature depends on. Implementations live in adapters/."""

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from audio_platform.modules.recordings.domain import Recording, StoredObject, UploadedPart


class RecordingRepository(Protocol):
    """System of record for recording metadata. Ownership is enforced inside the queries."""

    async def add(self, recording: Recording) -> None: ...

    async def get_for_owner(self, recording_id: UUID, owner_id: UUID) -> Recording | None: ...

    async def update(self, recording: Recording) -> None: ...


class AudioObjectStorage(Protocol):
    """Object storage for audio files. The client uploads parts directly via presigned URLs."""

    async def create_multipart_upload(self, key: str, content_type: str) -> str:
        """Start a multipart upload and return its upload ID."""
        ...

    async def presign_upload_part(self, key: str, upload_id: str, part_number: int, expires_in_s: int) -> str: ...

    async def complete_multipart_upload(self, key: str, upload_id: str, parts: Sequence[UploadedPart]) -> None: ...

    async def abort_multipart_upload(self, key: str, upload_id: str) -> None: ...

    async def head_object(self, key: str) -> StoredObject | None:
        """Return the committed object's metadata, or None if it does not exist."""
        ...
