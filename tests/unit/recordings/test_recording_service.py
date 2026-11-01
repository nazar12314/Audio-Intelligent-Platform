import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

from audio_platform.core.exceptions import (
    ConflictError,
    DependencyUnavailable,
    NotFoundError,
    ValidationFailed,
)
from audio_platform.modules.recordings.domain import (
    RecordingStatus,
    StoredObject,
    UploadedPart,
)
from audio_platform.modules.recordings.services import RecordingService
from tests.conftest import make_recording_service, make_settings
from tests.fakes.recordings import (
    FakeAudioObjectStorage,
    InMemoryRecordingStore,
    SignedSizeMismatch,
)

T0 = datetime(2026, 1, 1, 12, tzinfo=UTC)
OWNER = uuid.UUID("00000000-0000-7000-8000-00000000000a")
OTHER = uuid.UUID("00000000-0000-7000-8000-00000000000b")
AUDIO = b"ID3" + b"\x00" * 997


@pytest.fixture
def service(
    recordings_store: InMemoryRecordingStore, fake_storage: FakeAudioObjectStorage
) -> RecordingService:
    return make_recording_service(
        make_settings(), recordings_store, fake_storage, clock=lambda: T0
    )


async def _register(service: RecordingService, size: int = len(AUDIO)) -> uuid.UUID:
    registered = await service.register(
        OWNER, filename="call.mp3", content_type="audio/mpeg", size_bytes=size
    )
    return registered.recording.id


async def _upload(
    service: RecordingService,
    storage: FakeAudioObjectStorage,
    recording_id: uuid.UUID,
    data: bytes = AUDIO,
    *,
    enforce_length: bool = True,
) -> list[UploadedPart]:
    part = await service.presign_part(OWNER, recording_id, 1)
    etag = storage.put_part(part.url, data, enforce_length=enforce_length)
    return [UploadedPart(1, etag)]


async def test_register_stores_a_pending_recording_and_starts_the_upload(
    service: RecordingService,
    recordings_store: InMemoryRecordingStore,
    fake_storage: FakeAudioObjectStorage,
) -> None:
    registered = await service.register(
        OWNER, filename="call.mp3", content_type="audio/mpeg", size_bytes=len(AUDIO)
    )

    stored = recordings_store.rows[registered.recording.id]
    assert stored.status is RecordingStatus.PENDING_UPLOAD
    assert stored.part_count == 1
    assert fake_storage.uploads[stored.upload_id or ""].key == stored.object_key
    assert stored.object_key.startswith(f"users/{OWNER}/")


@pytest.mark.parametrize(
    ("content_type", "size"), [("video/mp4", 10), ("audio/mpeg", 3 * 1024**3)]
)
async def test_register_rejects_unsupported_type_or_size_before_touching_storage(
    service: RecordingService,
    fake_storage: FakeAudioObjectStorage,
    content_type: str,
    size: int,
) -> None:
    with pytest.raises(ValidationFailed):
        await service.register(
            OWNER, filename="x", content_type=content_type, size_bytes=size
        )
    assert fake_storage.uploads == {}


async def test_register_aborts_the_upload_when_saving_fails(
    service: RecordingService,
    recordings_store: InMemoryRecordingStore,
    fake_storage: FakeAudioObjectStorage,
) -> None:
    recordings_store.fail_next_commit = DependencyUnavailable("database unavailable")

    with pytest.raises(DependencyUnavailable):
        await _register(service)

    assert fake_storage.uploads == {}
    assert recordings_store.rows == {}


async def test_recordings_are_invisible_to_other_users(
    service: RecordingService,
) -> None:
    recording_id = await _register(service)

    with pytest.raises(NotFoundError):
        await service.get(OTHER, recording_id)
    with pytest.raises(NotFoundError):
        await service.presign_part(OTHER, recording_id, 1)
    with pytest.raises(NotFoundError):
        await service.complete(OTHER, recording_id, [UploadedPart(1, "e")])


async def test_presigned_part_expires_after_the_configured_ttl(
    service: RecordingService,
) -> None:
    recording_id = await _register(service)

    part = await service.presign_part(OWNER, recording_id, 1)

    assert part.expires_at == T0 + timedelta(seconds=service.url_ttl_s)
    with pytest.raises(ValidationFailed):
        await service.presign_part(OWNER, recording_id, 2)


async def test_complete_marks_the_recording_uploaded(
    service: RecordingService, fake_storage: FakeAudioObjectStorage
) -> None:
    recording_id = await _register(service)
    parts = await _upload(service, fake_storage, recording_id)

    recording = await service.complete(OWNER, recording_id, parts)

    assert recording.status is RecordingStatus.UPLOADED
    assert recording.uploaded_at == T0
    assert recording.etag
    assert (await service.get(OWNER, recording_id)).status is RecordingStatus.UPLOADED


async def test_retried_complete_returns_the_uploaded_recording(
    service: RecordingService, fake_storage: FakeAudioObjectStorage
) -> None:
    recording_id = await _register(service)
    parts = await _upload(service, fake_storage, recording_id)
    first = await service.complete(OWNER, recording_id, parts)

    again = await service.complete(OWNER, recording_id, parts)

    assert again == first


async def test_complete_recovers_when_storage_finished_but_the_record_did_not(
    service: RecordingService,
    recordings_store: InMemoryRecordingStore,
    fake_storage: FakeAudioObjectStorage,
) -> None:
    recording_id = await _register(service)
    parts = await _upload(service, fake_storage, recording_id)
    stored = recordings_store.rows[recording_id]
    await fake_storage.complete_multipart_upload(
        stored.object_key, stored.upload_id or "", parts
    )

    recording = await service.complete(OWNER, recording_id, parts)

    assert recording.status is RecordingStatus.UPLOADED


async def test_complete_with_a_wrong_etag_keeps_the_upload_open(
    service: RecordingService, fake_storage: FakeAudioObjectStorage
) -> None:
    recording_id = await _register(service)
    await _upload(service, fake_storage, recording_id)

    with pytest.raises(ValidationFailed, match="InvalidPart"):
        await service.complete(OWNER, recording_id, [UploadedPart(1, '"wrong"')])

    recording = await service.get(OWNER, recording_id)
    assert recording.status is RecordingStatus.PENDING_UPLOAD


async def test_complete_with_missing_parts_is_rejected(
    service: RecordingService, fake_storage: FakeAudioObjectStorage
) -> None:
    recording_id = await _register(service)

    with pytest.raises(ValidationFailed, match="exactly once"):
        await service.complete(OWNER, recording_id, [UploadedPart(2, "e")])


async def test_size_mismatch_fails_the_recording(
    service: RecordingService, fake_storage: FakeAudioObjectStorage
) -> None:
    recording_id = await _register(service, size=len(AUDIO) + 1)
    parts = await _upload(service, fake_storage, recording_id, enforce_length=False)

    recording = await service.complete(OWNER, recording_id, parts)

    assert recording.status is RecordingStatus.FAILED
    assert "size mismatch" in (recording.failure_reason or "")


async def test_expired_upload_fails_the_recording(
    service: RecordingService,
    recordings_store: InMemoryRecordingStore,
    fake_storage: FakeAudioObjectStorage,
) -> None:
    recording_id = await _register(service)
    parts = await _upload(service, fake_storage, recording_id)
    stored = recordings_store.rows[recording_id]
    await fake_storage.abort_multipart_upload(stored.object_key, stored.upload_id or "")

    recording = await service.complete(OWNER, recording_id, parts)

    assert recording.status is RecordingStatus.FAILED
    assert recording.failure_reason == "upload expired or was aborted"


async def test_abort_cancels_the_upload_and_is_idempotent(
    service: RecordingService, fake_storage: FakeAudioObjectStorage
) -> None:
    recording_id = await _register(service)

    first = await service.abort(OWNER, recording_id)
    second = await service.abort(OWNER, recording_id)

    assert first.status is second.status is RecordingStatus.ABORTED
    assert fake_storage.uploads == {}
    with pytest.raises(ConflictError):
        await service.presign_part(OWNER, recording_id, 1)


async def test_uploaded_recording_cannot_be_aborted(
    service: RecordingService, fake_storage: FakeAudioObjectStorage
) -> None:
    recording_id = await _register(service)
    await service.complete(
        OWNER, recording_id, await _upload(service, fake_storage, recording_id)
    )

    with pytest.raises(ConflictError):
        await service.abort(OWNER, recording_id)


async def test_storage_is_never_called_inside_a_transaction(
    service: RecordingService,
    recordings_store: InMemoryRecordingStore,
    fake_storage: FakeAudioObjectStorage,
) -> None:
    def no_open_transaction() -> None:
        assert recordings_store.open_transactions == 0, "storage call inside a tx"

    fake_storage.before_call = no_open_transaction
    completed = await _register(service)
    await service.complete(
        OWNER, completed, await _upload(service, fake_storage, completed)
    )
    aborted = await _register(service)
    await service.abort(OWNER, aborted)


async def test_size_mismatch_deletes_the_stored_object(
    service: RecordingService,
    recordings_store: InMemoryRecordingStore,
    fake_storage: FakeAudioObjectStorage,
) -> None:
    recording_id = await _register(service, size=10)
    parts = await _upload(
        service, fake_storage, recording_id, data=b"x" * 10_000, enforce_length=False
    )

    recording = await service.complete(OWNER, recording_id, parts)

    assert recording.status is RecordingStatus.FAILED
    assert recordings_store.rows[recording_id].object_key not in fake_storage.objects


async def test_failed_cleanup_is_logged_not_raised(
    service: RecordingService, fake_storage: FakeAudioObjectStorage
) -> None:
    recording_id = await _register(service, size=len(AUDIO) + 1)
    parts = await _upload(service, fake_storage, recording_id, enforce_length=False)
    fake_storage.fail_deletes = True

    recording = await service.complete(OWNER, recording_id, parts)

    assert recording.status is RecordingStatus.FAILED


async def test_abort_deletes_an_object_completed_but_never_recorded(
    service: RecordingService,
    recordings_store: InMemoryRecordingStore,
    fake_storage: FakeAudioObjectStorage,
) -> None:
    recording_id = await _register(service)
    parts = await _upload(service, fake_storage, recording_id)
    stored = recordings_store.rows[recording_id]
    await fake_storage.complete_multipart_upload(
        stored.object_key, stored.upload_id or "", parts
    )

    recording = await service.abort(OWNER, recording_id)

    assert recording.status is RecordingStatus.ABORTED
    assert stored.object_key not in fake_storage.objects


async def test_complete_racing_an_abort_is_a_conflict_and_leaves_no_object(
    service: RecordingService,
    recordings_store: InMemoryRecordingStore,
    fake_storage: FakeAudioObjectStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recording_id = await _register(service)
    parts = await _upload(service, fake_storage, recording_id)
    head_object = fake_storage.head_object

    async def head_then_abort_commits(key: str) -> StoredObject | None:
        stored = await head_object(key)
        recordings_store.rows[recording_id].mark_aborted(now=T0)
        return stored

    monkeypatch.setattr(fake_storage, "head_object", head_then_abort_commits)

    with pytest.raises(ConflictError):
        await service.complete(OWNER, recording_id, parts)

    assert recordings_store.rows[recording_id].status is RecordingStatus.ABORTED
    assert fake_storage.objects == {}


async def test_list_pages_through_the_owners_recordings(
    service: RecordingService,
) -> None:
    ids = [await _register(service) for _ in range(3)]
    await service.register(
        OTHER, filename="x.mp3", content_type="audio/mpeg", size_bytes=1
    )

    first = await service.list_recordings(OWNER, limit=2)
    second = await service.list_recordings(OWNER, limit=2, cursor=first.next_cursor)

    assert [r.id for r in first.items + second.items] == ids[::-1]
    assert first.next_cursor == ids[1]
    assert second.next_cursor is None


async def test_download_url_only_for_uploaded_recordings(
    service: RecordingService, fake_storage: FakeAudioObjectStorage
) -> None:
    recording_id = await _register(service)
    with pytest.raises(ConflictError):
        await service.presign_download(OWNER, recording_id)

    await service.complete(
        OWNER, recording_id, await _upload(service, fake_storage, recording_id)
    )
    download = await service.presign_download(OWNER, recording_id)

    assert fake_storage.get(download.url) == AUDIO
    assert download.expires_at == T0 + timedelta(seconds=service.url_ttl_s)


async def test_registration_includes_a_url_for_the_first_part(
    service: RecordingService, fake_storage: FakeAudioObjectStorage
) -> None:
    registered = await service.register(
        OWNER, filename="call.mp3", content_type="audio/mpeg", size_bytes=len(AUDIO)
    )
    etag = fake_storage.put_part(registered.first_part.url, AUDIO)

    recording = await service.complete(
        OWNER, registered.recording.id, [UploadedPart(1, etag)]
    )

    assert registered.first_part.part_number == 1
    assert recording.status is RecordingStatus.UPLOADED


@pytest.mark.parametrize("size", [len(AUDIO) + 1, len(AUDIO) - 1])
async def test_part_urls_only_accept_the_declared_size(
    service: RecordingService, fake_storage: FakeAudioObjectStorage, size: int
) -> None:
    recording_id = await _register(service, size=size)

    with pytest.raises(SignedSizeMismatch):
        await _upload(service, fake_storage, recording_id)


async def test_each_part_url_is_signed_for_that_parts_size(
    recordings_store: InMemoryRecordingStore, fake_storage: FakeAudioObjectStorage
) -> None:
    mib = 1024 * 1024
    service = make_recording_service(
        make_settings(upload={"part_size_bytes": 5 * mib}),
        recordings_store,
        fake_storage,
    )
    recording_id = await _register(service, size=12 * mib)

    urls = [(await service.presign_part(OWNER, recording_id, n)).url for n in (1, 2, 3)]

    sizes = [int(parse_qs(urlsplit(url).query)["contentLength"][0]) for url in urls]
    assert sizes == [5 * mib, 5 * mib, 2 * mib]


async def test_a_verified_upload_publishes_an_event_for_processing(
    service: RecordingService,
    recordings_store: InMemoryRecordingStore,
    fake_storage: FakeAudioObjectStorage,
) -> None:
    recording_id = await _register(service)
    await service.complete(
        OWNER, recording_id, await _upload(service, fake_storage, recording_id)
    )

    [(destination, event)] = recordings_store.outbox
    stored = recordings_store.rows[recording_id]
    assert (destination, event.type) == (
        "pipeline-events",
        "recordings.recording.uploaded",
    )
    assert event.data == {
        "recording_id": str(recording_id),
        "owner_id": str(OWNER),
        "object_key": stored.object_key,
        "content_type": "audio/mpeg",
        "size_bytes": len(AUDIO),
    }


async def test_a_failed_upload_publishes_nothing(
    service: RecordingService,
    recordings_store: InMemoryRecordingStore,
    fake_storage: FakeAudioObjectStorage,
) -> None:
    recording_id = await _register(service, size=len(AUDIO) + 1)
    parts = await _upload(service, fake_storage, recording_id, enforce_length=False)

    await service.complete(OWNER, recording_id, parts)

    assert recordings_store.outbox == []
