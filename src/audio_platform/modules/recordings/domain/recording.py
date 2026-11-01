"""Recording aggregate: an uploaded audio file and its ingestion lifecycle (Stage 1)."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class RecordingStatus(StrEnum):
    PENDING_UPLOAD = "pending_upload"  # record registered, multipart upload in progress
    UPLOADED = "uploaded"  # object committed in storage and verified
    ABORTED = "aborted"  # upload cancelled by the client or expired
    FAILED = "failed"  # upload completed but verification failed (size/type mismatch)


_TRANSITIONS: dict[RecordingStatus, frozenset[RecordingStatus]] = {
    RecordingStatus.PENDING_UPLOAD: frozenset(
        {RecordingStatus.UPLOADED, RecordingStatus.ABORTED, RecordingStatus.FAILED}
    ),
    RecordingStatus.UPLOADED: frozenset(),  # Stage 2 adds processing states from here
    RecordingStatus.ABORTED: frozenset(),
    RecordingStatus.FAILED: frozenset(),
}


class InvalidStatusTransition(Exception):
    def __init__(self, current: RecordingStatus, target: RecordingStatus) -> None:
        super().__init__(f"cannot move recording from {current} to {target}")
        self.current, self.target = current, target


@dataclass(frozen=True, slots=True)
class UploadedPart:
    part_number: int
    etag: str


@dataclass(frozen=True, slots=True)
class StoredObject:
    size_bytes: int
    content_type: str | None
    etag: str


def object_key_for(owner_id: UUID, recording_id: UUID) -> str:
    """
    Every user's audio lives under its own prefix; the key never contains
    client-supplied text.
    """
    return f"users/{owner_id}/recordings/{recording_id}/original"


@dataclass(slots=True)
class Recording:
    id: UUID
    owner_id: UUID
    filename: str
    content_type: str
    size_bytes: int  # declared by the client at registration; verified after upload
    object_key: str
    status: RecordingStatus
    created_at: datetime
    updated_at: datetime
    upload_id: str | None = None
    etag: str | None = None
    uploaded_at: datetime | None = None
    failure_reason: str | None = None

    @classmethod
    def register(
        cls,
        *,
        recording_id: UUID,
        owner_id: UUID,
        filename: str,
        content_type: str,
        size_bytes: int,
        now: datetime,
    ) -> Recording:
        return cls(
            id=recording_id,
            owner_id=owner_id,
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            object_key=object_key_for(owner_id, recording_id),
            status=RecordingStatus.PENDING_UPLOAD,
            created_at=now,
            updated_at=now,
        )

    def attach_upload(self, upload_id: str, *, now: datetime) -> None:
        self._require(RecordingStatus.PENDING_UPLOAD)
        self.upload_id, self.updated_at = upload_id, now

    def mark_uploaded(self, *, etag: str, now: datetime) -> None:
        self._move_to(RecordingStatus.UPLOADED, now)
        self.etag, self.uploaded_at = etag, now

    def mark_aborted(self, *, now: datetime) -> None:
        self._move_to(RecordingStatus.ABORTED, now)

    def mark_failed(self, reason: str, *, now: datetime) -> None:
        self._move_to(RecordingStatus.FAILED, now)
        self.failure_reason = reason

    def _require(self, status: RecordingStatus) -> None:
        if self.status is not status:
            raise InvalidStatusTransition(self.status, status)

    def _move_to(self, target: RecordingStatus, now: datetime) -> None:
        if target not in _TRANSITIONS[self.status]:
            raise InvalidStatusTransition(self.status, target)
        self.status, self.updated_at = target, now
