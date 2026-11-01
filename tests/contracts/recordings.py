"""
Port contract suites. Subclass one per implementation and provide its fixtures, so
fakes and real adapters are held to the same behaviour.
"""

import os
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import pytest

from audio_platform.core.exceptions import ConflictError
from audio_platform.modules.recordings.domain import Recording, UploadedPart
from audio_platform.modules.recordings.ports import (
    AudioObjectStorage,
    PartsRejected,
    UnitOfWorkFactory,
    UploadNotFound,
)

PartUploader = Callable[[str, bytes], Awaitable[str]]  # presigned URL, data -> ETag
Downloader = Callable[[str], Awaitable[bytes]]  # presigned URL -> body
MIB = 1024 * 1024


class StorageRejectedPut(Exception):
    """Raised by a PartUploader when storage refuses the PUT."""


def _key() -> str:
    return f"users/{uuid.uuid4()}/recordings/{uuid.uuid4()}/original"


class AudioObjectStorageContract:
    """
    Fixtures: `storage: AudioObjectStorage`, `upload_part: PartUploader`,
    `download: Downloader`.
    """

    async def _upload(
        self,
        storage: AudioObjectStorage,
        upload_part: PartUploader,
        chunks: list[bytes],
    ) -> tuple[str, str, list[UploadedPart]]:
        key = _key()
        upload_id = await storage.create_multipart_upload(key, "audio/mpeg")
        parts = []
        for number, chunk in enumerate(chunks, start=1):
            url = await storage.presign_upload_part(
                key, upload_id, number, 300, content_length=len(chunk)
            )
            parts.append(UploadedPart(number, await upload_part(url, chunk)))
        return key, upload_id, parts

    async def test_multipart_upload_round_trip(
        self, storage: AudioObjectStorage, upload_part: PartUploader
    ) -> None:
        chunks = [os.urandom(5 * MIB), os.urandom(1000)]
        key, upload_id, parts = await self._upload(storage, upload_part, chunks)

        await storage.complete_multipart_upload(key, upload_id, parts)

        stored = await storage.head_object(key)
        assert stored is not None
        assert stored.size_bytes == 5 * MIB + 1000
        assert stored.content_type == "audio/mpeg"

    async def test_deleted_object_is_gone(
        self, storage: AudioObjectStorage, upload_part: PartUploader
    ) -> None:
        key, upload_id, parts = await self._upload(storage, upload_part, [b"audio"])
        await storage.complete_multipart_upload(key, upload_id, parts)
        stored = await storage.head_object(key)
        assert stored is not None

        await storage.delete_object(key, version_id=stored.version_id)

        assert await storage.head_object(key) is None
        await storage.delete_object(key)  # deleting a missing object is not an error

    async def test_presigned_download_returns_the_stored_bytes(
        self,
        storage: AudioObjectStorage,
        upload_part: PartUploader,
        download: Downloader,
    ) -> None:
        body = os.urandom(2048)
        key, upload_id, parts = await self._upload(storage, upload_part, [body])
        await storage.complete_multipart_upload(key, upload_id, parts)

        assert await download(await storage.presign_download(key, 300)) == body

    @pytest.mark.parametrize("body_size", [999, 1001])
    async def test_part_url_only_accepts_the_signed_size(
        self, storage: AudioObjectStorage, upload_part: PartUploader, body_size: int
    ) -> None:
        key = _key()
        upload_id = await storage.create_multipart_upload(key, "audio/mpeg")
        url = await storage.presign_upload_part(
            key, upload_id, 1, 300, content_length=1000
        )

        with pytest.raises(StorageRejectedPut):
            await upload_part(url, os.urandom(body_size))
        assert await upload_part(url, os.urandom(1000))
        await storage.abort_multipart_upload(key, upload_id)

    async def test_missing_object_is_none(self, storage: AudioObjectStorage) -> None:
        assert await storage.head_object(_key()) is None

    async def test_wrong_etag_is_rejected(
        self, storage: AudioObjectStorage, upload_part: PartUploader
    ) -> None:
        key, upload_id, _ = await self._upload(storage, upload_part, [b"audio"])

        with pytest.raises(PartsRejected):
            await storage.complete_multipart_upload(
                key, upload_id, [UploadedPart(1, '"0123456789abcdef0123456789abcdef"')]
            )

    async def test_small_non_last_part_is_rejected(
        self, storage: AudioObjectStorage, upload_part: PartUploader
    ) -> None:
        key, upload_id, parts = await self._upload(
            storage, upload_part, [b"too small", b"last"]
        )

        with pytest.raises(PartsRejected):
            await storage.complete_multipart_upload(key, upload_id, parts)

    async def test_aborted_upload_is_gone(
        self, storage: AudioObjectStorage, upload_part: PartUploader
    ) -> None:
        key, upload_id, parts = await self._upload(storage, upload_part, [b"audio"])

        await storage.abort_multipart_upload(key, upload_id)

        with pytest.raises(UploadNotFound):
            await storage.complete_multipart_upload(key, upload_id, parts)
        with pytest.raises(UploadNotFound):
            await storage.abort_multipart_upload(key, upload_id)


def _recording(owner_id: uuid.UUID | None = None) -> Recording:
    now = datetime.now(UTC).replace(microsecond=0)
    recording = Recording.register(
        recording_id=uuid.uuid7(),
        owner_id=owner_id or uuid.uuid7(),
        filename="call.mp3",
        content_type="audio/mpeg",
        size_bytes=1234,
        part_size_bytes=16 * MIB,
        now=now,
    )
    recording.attach_upload("upload-1", now=now)
    return recording


class RecordingUnitOfWorkContract:
    """Fixture: `uow: UnitOfWorkFactory`, backed by an empty store."""

    async def test_committed_recording_round_trips(
        self, uow: UnitOfWorkFactory
    ) -> None:
        recording = _recording()
        async with uow() as tx:
            await tx.recordings.add(recording)
            await tx.commit()

        async with uow() as tx:
            loaded = await tx.recordings.get_for_owner(recording.id, recording.owner_id)
        assert loaded == recording

    async def test_other_owners_cannot_load_it(self, uow: UnitOfWorkFactory) -> None:
        recording = _recording()
        async with uow() as tx:
            await tx.recordings.add(recording)
            await tx.commit()

        async with uow() as tx:
            assert await tx.recordings.get_for_owner(recording.id, uuid.uuid7()) is None

    async def test_update_persists_status_changes(self, uow: UnitOfWorkFactory) -> None:
        recording = _recording()
        async with uow() as tx:
            await tx.recordings.add(recording)
            await tx.commit()

        recording.mark_uploaded(etag='"abc-1"', now=recording.created_at)
        async with uow() as tx:
            await tx.recordings.update(recording)
            await tx.commit()

        async with uow() as tx:
            loaded = await tx.recordings.get_for_owner(
                recording.id, recording.owner_id, for_update=True
            )
        assert loaded == recording

    async def test_uncommitted_changes_are_discarded(
        self, uow: UnitOfWorkFactory
    ) -> None:
        recording = _recording()
        async with uow() as tx:
            await tx.recordings.add(recording)

        async with uow() as tx:
            assert (
                await tx.recordings.get_for_owner(recording.id, recording.owner_id)
                is None
            )

    async def test_duplicate_recording_is_a_conflict(
        self, uow: UnitOfWorkFactory
    ) -> None:
        recording = _recording()
        async with uow() as tx:
            await tx.recordings.add(recording)
            await tx.commit()

        with pytest.raises(ConflictError):
            async with uow() as tx:
                await tx.recordings.add(recording)
                await tx.commit()

    async def test_list_is_newest_first_paginated_and_owner_scoped(
        self, uow: UnitOfWorkFactory
    ) -> None:
        owner = uuid.uuid7()
        mine = [_recording(owner) for _ in range(3)]
        async with uow() as tx:
            for recording in [*mine, _recording()]:
                await tx.recordings.add(recording)
            await tx.commit()

        async with uow() as tx:
            first = await tx.recordings.list_for_owner(owner, limit=2)
            rest = await tx.recordings.list_for_owner(
                owner, limit=2, before_id=first[-1].id
            )

        assert [r.id for r in first + rest] == [r.id for r in reversed(mine)]
