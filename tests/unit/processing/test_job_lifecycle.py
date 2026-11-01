import uuid
from datetime import UTC, datetime

import pytest

from audio_platform.modules.processing.domain import (
    AudioInfo,
    InvalidAudio,
    InvalidJobTransition,
    JobStatus,
    ProcessingJob,
    StageName,
    StageStatus,
    validate_audio,
)

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _job() -> ProcessingJob:
    return ProcessingJob.start(
        job_id=uuid.uuid7(),
        recording_id=uuid.uuid7(),
        owner_id=uuid.uuid7(),
        object_key="users/u/recordings/r/original",
        now=T0,
    )


def test_new_job_runs_with_a_pending_vad_stage() -> None:
    job = _job()
    assert job.status is JobStatus.RUNNING
    assert job.stage(StageName.VAD).status is StageStatus.PENDING


def test_each_attempt_is_counted() -> None:
    job = _job()
    job.begin_stage(StageName.VAD, now=T0)
    job.record_retryable_error(StageName.VAD, "timeout", now=T0)
    job.begin_stage(StageName.VAD, now=T0)

    stage = job.stage(StageName.VAD)
    assert (stage.status, stage.attempts, stage.error) == (
        StageStatus.RUNNING,
        2,
        "timeout",
    )


def test_finished_stage_cannot_restart() -> None:
    job = _job()
    job.begin_stage(StageName.VAD, now=T0)
    job.succeed_stage(StageName.VAD, {"speech_detected": True}, now=T0)

    with pytest.raises(InvalidJobTransition):
        job.begin_stage(StageName.VAD, now=T0)


def test_finished_job_rejects_changes() -> None:
    job = _job()
    job.complete(speech_detected=False, now=T0)

    with pytest.raises(InvalidJobTransition):
        job.fail("late failure", now=T0)
    assert (job.status, job.speech_detected) == (JobStatus.COMPLETED, False)


@pytest.mark.parametrize(
    ("info", "message"),
    [
        (AudioInfo("wav", "pcm", 0, 1, 1.0), "no samples"),
        (AudioInfo("wav", "pcm", 16000, 1, 0.0), "empty"),
        (AudioInfo("wav", "pcm", 16000, 1, 3601.0), "limit is 3600"),
    ],
)
def test_invalid_audio_is_rejected(info: AudioInfo, message: str) -> None:
    with pytest.raises(InvalidAudio, match=message):
        validate_audio(info, max_duration_s=3600)


def test_unknown_duration_is_checked_later() -> None:
    validate_audio(AudioInfo("ogg", "opus", 48000, 2, None), max_duration_s=3600)
