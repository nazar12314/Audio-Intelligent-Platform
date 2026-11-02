import json
import uuid
from datetime import UTC, datetime

import pytest

from audio_platform.modules.processing.domain import (
    ProcessingJob,
    SpeechSegment,
    StageName,
    StageStatus,
)
from audio_platform.modules.processing.ports import AnalysisTimedOut
from audio_platform.modules.processing.services import (
    AsrWorker,
    AsrWorkerConfig,
    EventTypes,
)
from tests.fakes.processing import (
    FakeTranscriber,
    InMemoryArtifactStorage,
    InMemoryProcessingStore,
)

T0 = datetime(2026, 1, 1, tzinfo=UTC)
NORMALIZED = "users/u/recordings/r/normalized.wav"
SEGMENTS = "users/u/recordings/r/vad.json"
TRANSCRIPT = "users/u/recordings/r/transcript.json"
WORDS = "users/u/recordings/r/words.json"
SPEECH = [{"start_ms": 290, "end_ms": 990}, {"start_ms": 1500, "end_ms": 1900}]


def _job_after_vad(store: InMemoryProcessingStore) -> ProcessingJob:
    job = ProcessingJob.start(
        job_id=uuid.uuid7(),
        recording_id=uuid.uuid7(),
        owner_id=uuid.uuid7(),
        object_key="users/u/recordings/r/original",
        now=T0,
    )
    job.begin_stage(StageName.VAD, now=T0)
    job.succeed_stage(
        StageName.VAD,
        {
            "speech_detected": True,
            "normalized_key": NORMALIZED,
            "segments_key": SEGMENTS,
        },
        now=T0,
    )
    job.record_speech(True, now=T0)
    job.add_stage(StageName.ASR, now=T0)
    store.jobs[job.id] = job
    return job


@pytest.fixture
def job(
    processing_store: InMemoryProcessingStore,
    artifact_storage: InMemoryArtifactStorage,
) -> ProcessingJob:
    artifact_storage.objects[NORMALIZED] = b"RIFF normalized audio"
    artifact_storage.objects[SEGMENTS] = json.dumps({"segments": SPEECH}).encode()
    return _job_after_vad(processing_store)


@pytest.fixture
def transcriber() -> FakeTranscriber:
    return FakeTranscriber(language="uk")


@pytest.fixture
def worker(
    processing_store: InMemoryProcessingStore,
    artifact_storage: InMemoryArtifactStorage,
    transcriber: FakeTranscriber,
) -> AsrWorker:
    return AsrWorker(
        processing_store.unit_of_work,
        artifact_storage,
        transcriber,
        AsrWorkerConfig(model="small", max_attempts=3),
    )


async def test_the_speech_found_by_vad_is_transcribed_and_stored(
    job: ProcessingJob,
    worker: AsrWorker,
    transcriber: FakeTranscriber,
    processing_store: InMemoryProcessingStore,
    artifact_storage: InMemoryArtifactStorage,
) -> None:
    await worker.handle({"job_id": str(job.id)}, receive_count=1)

    assert transcriber.calls == [[SpeechSegment(290, 990), SpeechSegment(1500, 1900)]]
    stage = processing_store.jobs[job.id].stage(StageName.ASR)
    assert (stage.status, stage.attempts) == (StageStatus.SUCCEEDED, 1)
    assert stage.result == {
        "language": "uk",
        "language_probability": 0.97,
        "segment_count": 2,
        "model": "small",
        "transcript_key": TRANSCRIPT,
        "words_key": WORDS,
    }
    document = json.loads(artifact_storage.objects[TRANSCRIPT])
    assert document["language"] == "uk"
    assert document["text"] == "segment 1 segment 2"
    # What the API serves stays small; word timings live in their own artifact.
    assert document["version"] == 3
    assert document["segments"][0] == {
        "start_ms": 290,
        "end_ms": 990,
        "text": "segment 1",
    }
    words = json.loads(artifact_storage.objects[WORDS])
    assert words["segments"][0] == [
        {"start_ms": 290, "end_ms": 990, "text": " segment 1", "probability": 0.9}
    ]
    assert len(words["segments"]) == len(document["segments"])
    [(destination, event)] = processing_store.outbox
    assert (destination, event.type, event.data) == (
        "pipeline-events",
        EventTypes.ASR_COMPLETED,
        {"job_id": str(job.id), "language": "uk"},
    )


async def test_transient_errors_are_retried_by_redelivery(
    job: ProcessingJob,
    worker: AsrWorker,
    processing_store: InMemoryProcessingStore,
    artifact_storage: InMemoryArtifactStorage,
) -> None:
    artifact_storage.fail_downloads = 1

    with pytest.raises(Exception, match="object storage unavailable"):
        await worker.handle({"job_id": str(job.id)}, receive_count=1)
    stage = processing_store.jobs[job.id].stage(StageName.ASR)
    assert (stage.status, stage.attempts) == (StageStatus.RUNNING, 1)
    assert processing_store.outbox == []

    await worker.handle({"job_id": str(job.id)}, receive_count=2)
    stage = processing_store.jobs[job.id].stage(StageName.ASR)
    assert (stage.status, stage.attempts) == (StageStatus.SUCCEEDED, 2)


@pytest.mark.parametrize(("attempt", "retried"), [(1, True), (3, False)])
async def test_timeouts_are_retried_then_recorded(
    job: ProcessingJob,
    worker: AsrWorker,
    transcriber: FakeTranscriber,
    processing_store: InMemoryProcessingStore,
    attempt: int,
    retried: bool,
) -> None:
    transcriber.error = AnalysisTimedOut("transcription exceeded 3000 s")

    if retried:
        with pytest.raises(AnalysisTimedOut):
            await worker.handle({"job_id": str(job.id)}, receive_count=attempt)
        assert processing_store.outbox == []
    else:
        await worker.handle({"job_id": str(job.id)}, receive_count=attempt)
        [event] = processing_store.events(EventTypes.ASR_FAILED)
        assert event.data["error"] == (
            "gave up after 3 attempts (AnalysisTimedOut: transcription exceeded 3000 s)"
        )
        stage = processing_store.jobs[job.id].stage(StageName.ASR)
        assert stage.status is StageStatus.FAILED


async def test_missing_vad_segments_fail_after_the_last_attempt(
    job: ProcessingJob,
    worker: AsrWorker,
    processing_store: InMemoryProcessingStore,
    artifact_storage: InMemoryArtifactStorage,
) -> None:
    del artifact_storage.objects[SEGMENTS]

    await worker.handle({"job_id": str(job.id)}, receive_count=3)

    [event] = processing_store.events(EventTypes.ASR_FAILED)
    assert f"LookupError: {SEGMENTS} is missing" in event.data["error"]


async def test_redelivered_or_unexpected_tasks_do_nothing(
    job: ProcessingJob,
    worker: AsrWorker,
    transcriber: FakeTranscriber,
    processing_store: InMemoryProcessingStore,
) -> None:
    await worker.handle({"job_id": str(job.id)}, receive_count=1)
    await worker.handle({"job_id": str(job.id)}, receive_count=2)
    await worker.handle({"job_id": str(uuid.uuid7())}, receive_count=1)

    without_asr = ProcessingJob.start(
        job_id=uuid.uuid7(),
        recording_id=uuid.uuid7(),
        owner_id=uuid.uuid7(),
        object_key="users/u/recordings/x/original",
        now=T0,
    )
    processing_store.jobs[without_asr.id] = without_asr
    await worker.handle({"job_id": str(without_asr.id)}, receive_count=1)

    assert len(transcriber.calls) == 1
    assert len(processing_store.outbox) == 1


async def test_storage_is_never_called_inside_a_transaction(
    job: ProcessingJob,
    worker: AsrWorker,
    processing_store: InMemoryProcessingStore,
    artifact_storage: InMemoryArtifactStorage,
) -> None:
    def no_open_transaction() -> None:
        assert processing_store.open_transactions == 0, "storage call inside a tx"

    artifact_storage.before_call = no_open_transaction

    await worker.handle({"job_id": str(job.id)}, receive_count=1)

    assert processing_store.events(EventTypes.ASR_COMPLETED)
