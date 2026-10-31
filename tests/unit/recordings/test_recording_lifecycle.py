import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from audio_platform.modules.recordings.domain import InvalidStatusTransition, Recording, RecordingStatus, object_key_for

T0 = datetime(2026, 1, 1, tzinfo=UTC)
OWNER = uuid.UUID("00000000-0000-7000-8000-000000000001")
REC = uuid.UUID("00000000-0000-7000-8000-000000000002")


def _registered() -> Recording:
    return Recording.register(
        recording_id=REC, owner_id=OWNER, filename="call.mp3", content_type="audio/mpeg", size_bytes=1024, now=T0
    )


def test_register_starts_pending_under_the_owner_prefix() -> None:
    rec = _registered()
    assert rec.status is RecordingStatus.PENDING_UPLOAD
    assert rec.object_key == f"users/{OWNER}/recordings/{REC}/original"


def test_object_key_never_contains_the_client_filename() -> None:
    assert "call.mp3" not in object_key_for(OWNER, REC)


def test_pending_recording_can_be_marked_uploaded() -> None:
    rec = _registered()
    rec.attach_upload("upload-1", now=T0)
    later = T0 + timedelta(minutes=5)

    rec.mark_uploaded(etag='"abc-2"', now=later)

    assert rec.status is RecordingStatus.UPLOADED
    assert (rec.upload_id, rec.etag, rec.uploaded_at, rec.updated_at) == ("upload-1", '"abc-2"', later, later)


def test_failed_recording_keeps_the_reason() -> None:
    rec = _registered()
    rec.mark_failed("size mismatch", now=T0)
    assert (rec.status, rec.failure_reason) == (RecordingStatus.FAILED, "size mismatch")


@pytest.mark.parametrize(
    "finish",
    [
        lambda rec: rec.mark_uploaded(etag="e", now=T0),
        lambda rec: rec.mark_aborted(now=T0),
        lambda rec: rec.mark_failed("x", now=T0),
    ],
    ids=["uploaded", "aborted", "failed"],
)
def test_terminal_states_reject_further_transitions(finish: Callable[[Recording], None]) -> None:
    rec = _registered()
    finish(rec)

    with pytest.raises(InvalidStatusTransition):
        rec.mark_uploaded(etag="e", now=T0)
    with pytest.raises(InvalidStatusTransition):
        rec.attach_upload("again", now=T0)
