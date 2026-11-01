from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from audio_platform.modules.recordings.domain import (
    Recording,
    RecordingStatus,
    UploadedPart,
)

MAX_PARTS = 10_000

Filename = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=255,
        pattern=r"^[^/\\\x00-\x1f\x7f]+$",  # a bare name: no paths, no control chars
    ),
]
ContentType = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, to_lower=True, min_length=3, max_length=100
    ),
]


class RegisterRecordingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: Filename
    content_type: ContentType
    size_bytes: int = Field(gt=0)


class RecordingOut(BaseModel):
    id: UUID
    filename: str
    content_type: str
    size_bytes: int
    status: RecordingStatus
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime
    uploaded_at: datetime | None

    @classmethod
    def from_domain(cls, recording: Recording) -> RecordingOut:
        return cls(
            id=recording.id,
            filename=recording.filename,
            content_type=recording.content_type,
            size_bytes=recording.size_bytes,
            status=recording.status,
            failure_reason=recording.failure_reason,
            created_at=recording.created_at,
            updated_at=recording.updated_at,
            uploaded_at=recording.uploaded_at,
        )


class RegisteredRecordingOut(BaseModel):
    recording: RecordingOut
    upload: UploadPlanOut


class RecordingPageOut(BaseModel):
    items: list[RecordingOut]
    next_cursor: UUID | None


class DownloadUrlOut(BaseModel):
    url: str
    expires_at: datetime


class PartUploadUrlOut(BaseModel):
    part_number: int
    url: str
    expires_at: datetime


class UploadPlanOut(BaseModel):
    part_size_bytes: int
    part_count: int
    url_ttl_s: int
    first_part: PartUploadUrlOut


class CompletedPartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    part_number: int = Field(ge=1, le=MAX_PARTS)
    etag: str = Field(min_length=1, max_length=128)

    def to_domain(self) -> UploadedPart:
        return UploadedPart(part_number=self.part_number, etag=self.etag)


class CompleteUploadIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parts: list[CompletedPartIn] = Field(min_length=1, max_length=MAX_PARTS)
