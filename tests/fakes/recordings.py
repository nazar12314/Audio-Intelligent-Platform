import copy
import hashlib
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from types import TracebackType
from typing import Self
from urllib.parse import parse_qs, urlsplit

from audio_platform.core.exceptions import ConflictError
from audio_platform.modules.recordings.domain import (
    Recording,
    StoredObject,
    UploadedPart,
)
from audio_platform.modules.recordings.ports import PartsRejected, UploadNotFound

S3_MIN_PART_SIZE = 5 * 1024 * 1024


class SignedSizeMismatch(Exception):
    """What S3 answers (403) when a PUT body differs from the signed length."""


class InMemoryRecordingRepository:
    def __init__(self, rows: dict[uuid.UUID, Recording]) -> None:
        self._rows = rows

    async def add(self, recording: Recording) -> None:
        if recording.id in self._rows or any(
            r.object_key == recording.object_key for r in self._rows.values()
        ):
            raise ConflictError("recording conflicts with an existing one")
        self._rows[recording.id] = copy.deepcopy(recording)

    async def get_for_owner(
        self, recording_id: uuid.UUID, owner_id: uuid.UUID, *, for_update: bool = False
    ) -> Recording | None:
        row = self._rows.get(recording_id)
        if row is None or row.owner_id != owner_id:
            return None
        return copy.deepcopy(row)

    async def list_for_owner(
        self, owner_id: uuid.UUID, *, limit: int, before_id: uuid.UUID | None = None
    ) -> list[Recording]:
        rows = sorted(
            (
                r
                for r in self._rows.values()
                if r.owner_id == owner_id and (before_id is None or r.id < before_id)
            ),
            key=lambda r: r.id,
            reverse=True,
        )
        return copy.deepcopy(rows[:limit])

    async def update(self, recording: Recording) -> None:
        row = self._rows.get(recording.id)
        if row is not None and row.owner_id == recording.owner_id:
            self._rows[recording.id] = copy.deepcopy(recording)


class InMemoryRecordingStore:
    """Committed state shared by every unit of work, like a database."""

    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, Recording] = {}
        self.fail_next_commit: Exception | None = None
        self.open_transactions = 0

    def unit_of_work(self) -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(self)


class InMemoryUnitOfWork:
    def __init__(self, store: InMemoryRecordingStore) -> None:
        self._store = store
        self._working: dict[uuid.UUID, Recording] = {}

    @property
    def recordings(self) -> InMemoryRecordingRepository:
        return self._repository

    async def __aenter__(self) -> Self:
        self._store.open_transactions += 1
        self._working = copy.deepcopy(self._store.rows)
        self._repository = InMemoryRecordingRepository(self._working)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._store.open_transactions -= 1
        self._working = {}

    async def commit(self) -> None:
        if (error := self._store.fail_next_commit) is not None:
            self._store.fail_next_commit = None
            raise error
        self._store.rows = copy.deepcopy(self._working)


@dataclass
class _Upload:
    key: str
    content_type: str
    parts: dict[int, bytes] = field(default_factory=dict)


def _etag(data: bytes) -> str:
    return f'"{hashlib.md5(data, usedforsecurity=False).hexdigest()}"'


class FakeAudioObjectStorage:
    """In-memory storage that enforces the multipart rules S3 does."""

    base_url = "https://storage.test"

    def __init__(self) -> None:
        self.uploads: dict[str, _Upload] = {}
        self.objects: dict[str, StoredObject] = {}
        self.bodies: dict[str, bytes] = {}
        self.fail_deletes = False
        self.before_call: Callable[[], None] = lambda: None

    async def _io(self) -> None:
        self.before_call()

    async def create_multipart_upload(self, key: str, content_type: str) -> str:
        await self._io()
        upload_id = uuid.uuid4().hex
        self.uploads[upload_id] = _Upload(key=key, content_type=content_type)
        return upload_id

    async def presign_upload_part(
        self,
        key: str,
        upload_id: str,
        part_number: int,
        expires_in_s: int,
        *,
        content_length: int,
    ) -> str:
        return (
            f"{self.base_url}/{key}?uploadId={upload_id}&partNumber={part_number}"
            f"&contentLength={content_length}&expires={expires_in_s}"
        )

    async def presign_download(self, key: str, expires_in_s: int) -> str:
        return f"{self.base_url}/{key}?download=1&expires={expires_in_s}"

    def get(self, url: str) -> bytes:
        """What a client's GET to a presigned download URL returns."""
        return self.bodies[urlsplit(url).path.removeprefix("/")]

    def put_part(self, url: str, data: bytes, *, enforce_length: bool = True) -> str:
        """
        What a client's PUT to a presigned URL does; returns the ETag.
        `enforce_length=False` mimics storage that ignores the signed size.
        """
        query = parse_qs(urlsplit(url).query)
        if enforce_length and len(data) != int(query["contentLength"][0]):
            raise SignedSizeMismatch
        upload = self.uploads.get(query["uploadId"][0])
        if upload is None:
            raise UploadNotFound
        upload.parts[int(query["partNumber"][0])] = data
        return _etag(data)

    async def complete_multipart_upload(
        self, key: str, upload_id: str, parts: Sequence[UploadedPart]
    ) -> None:
        await self._io()
        upload = self.uploads.get(upload_id)
        if upload is None or upload.key != key:
            raise UploadNotFound
        numbers = [p.part_number for p in parts]
        if numbers != sorted(set(numbers)):
            raise PartsRejected("storage rejected the parts: InvalidPartOrder")
        for part in parts:
            data = upload.parts.get(part.part_number)
            if data is None or _etag(data).strip('"') != part.etag.strip('"'):
                raise PartsRejected("storage rejected the parts: InvalidPart")
        if any(len(upload.parts[n]) < S3_MIN_PART_SIZE for n in numbers[:-1]):
            raise PartsRejected("storage rejected the parts: EntityTooSmall")

        body = b"".join(upload.parts[n] for n in numbers)
        self.bodies[key] = body
        self.objects[key] = StoredObject(
            size_bytes=len(body),
            content_type=upload.content_type,
            etag=f'"{_etag(body).strip(chr(34))}-{len(numbers)}"',
        )
        del self.uploads[upload_id]

    async def abort_multipart_upload(self, key: str, upload_id: str) -> None:
        await self._io()
        upload = self.uploads.pop(upload_id, None)
        if upload is None or upload.key != key:
            raise UploadNotFound

    async def head_object(self, key: str) -> StoredObject | None:
        await self._io()
        return self.objects.get(key)

    async def delete_object(self, key: str, *, version_id: str | None = None) -> None:
        await self._io()
        if self.fail_deletes:
            raise OSError("storage unavailable")
        self.objects.pop(key, None)
        self.bodies.pop(key, None)
