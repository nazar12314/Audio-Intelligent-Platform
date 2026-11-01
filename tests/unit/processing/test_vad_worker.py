import json
import uuid
from datetime import UTC, datetime

import pytest

from audio_platform.modules.processing.adapters.analyzer import (
    InProcessAudioAnalyzer,
)
from audio_platform.modules.processing.domain import (
    ProcessingJob,
    StageName,
    StageStatus,
    VadParameters,
)
from audio_platform.modules.processing.ports import AnalysisTimedOut
from audio_platform.modules.processing.services import (
    EventTypes,
    VadWorker,
    VadWorkerConfig,
)
from tests.fakes.processing import (
    FakeDecoder,
    FakeSpeechModel,
    InMemoryArtifactStorage,
    InMemoryProcessingStore,
)

KEY = "users/u/recordings/r/original"
SPEECH = [0.0] * 10 + [0.9] * 20 + [0.0] * 32  # ~2 s, speech from 320 ms to 960 ms
SILENCE = [0.0] * 62


@pytest.fixture
def job(processing_store: InMemoryProcessingStore) -> ProcessingJob:
    job = ProcessingJob.start(
        job_id=uuid.uuid7(),
        recording_id=uuid.uuid7(),
        owner_id=uuid.uuid7(),
        object_key=KEY,
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    processing_store.jobs[job.id] = job
    return job


@pytest.fixture
def decoder() -> FakeDecoder:
    return FakeDecoder(seconds=2.0)


def make_worker(
    store: InMemoryProcessingStore,
    storage: InMemoryArtifactStorage,
    decoder: FakeDecoder,
    probabilities: list[float] = SPEECH,
) -> VadWorker:
    storage.objects.setdefault(KEY, b"original audio bytes")
    return VadWorker(
        store.unit_of_work,
        storage,
        InProcessAudioAnalyzer(decoder, FakeSpeechModel(probabilities)),
        VadWorkerConfig(params=VadParameters(), max_duration_s=3600, max_attempts=3),
    )


async def test_speech_is_detected_and_artifacts_are_stored(
    job: ProcessingJob,
    processing_store: InMemoryProcessingStore,
    artifact_storage: InMemoryArtifactStorage,
    decoder: FakeDecoder,
) -> None:
    worker = make_worker(processing_store, artifact_storage, decoder)

    await worker.handle({"job_id": str(job.id)}, receive_count=1)

    stage = processing_store.jobs[job.id].stage(StageName.VAD)
    assert (stage.status, stage.attempts) == (StageStatus.SUCCEEDED, 1)
    assert stage.result is not None
    assert stage.result["speech_detected"] is True
    assert stage.result["source"]["sample_rate"] == 44_100
    document = json.loads(artifact_storage.objects["users/u/recordings/r/vad.json"])
    assert document["segments"] == [{"start_ms": 290, "end_ms": 990}]
    assert artifact_storage.objects["users/u/recordings/r/normalized.wav"].startswith(
        b"RIFF"
    )
    [event] = processing_store.events(EventTypes.VAD_COMPLETED)
    assert event.data == {"job_id": str(job.id), "speech_detected": True}


async def test_silence_completes_without_speech(
    job: ProcessingJob,
    processing_store: InMemoryProcessingStore,
    artifact_storage: InMemoryArtifactStorage,
    decoder: FakeDecoder,
) -> None:
    worker = make_worker(processing_store, artifact_storage, decoder, SILENCE)

    await worker.handle({"job_id": str(job.id)}, receive_count=1)

    [event] = processing_store.events(EventTypes.VAD_COMPLETED)
    assert event.data["speech_detected"] is False


async def test_invalid_audio_fails_without_retrying(
    job: ProcessingJob,
    processing_store: InMemoryProcessingStore,
    artifact_storage: InMemoryArtifactStorage,
    decoder: FakeDecoder,
) -> None:
    decoder.invalid = "no audio stream"
    worker = make_worker(processing_store, artifact_storage, decoder)

    await worker.handle({"job_id": str(job.id)}, receive_count=1)

    stage = processing_store.jobs[job.id].stage(StageName.VAD)
    assert (stage.status, stage.error) == (
        StageStatus.FAILED,
        "invalid audio: no audio stream",
    )
    [event] = processing_store.events(EventTypes.VAD_FAILED)
    assert event.data["error"] == "invalid audio: no audio stream"


async def test_transient_errors_are_retried_by_redelivery(
    job: ProcessingJob,
    processing_store: InMemoryProcessingStore,
    artifact_storage: InMemoryArtifactStorage,
    decoder: FakeDecoder,
) -> None:
    worker = make_worker(processing_store, artifact_storage, decoder)
    artifact_storage.fail_downloads = 1

    with pytest.raises(Exception, match="object storage unavailable"):
        await worker.handle({"job_id": str(job.id)}, receive_count=1)
    stage = processing_store.jobs[job.id].stage(StageName.VAD)
    assert (stage.status, stage.attempts) == (StageStatus.RUNNING, 1)
    assert processing_store.outbox == []

    await worker.handle({"job_id": str(job.id)}, receive_count=2)
    stage = processing_store.jobs[job.id].stage(StageName.VAD)
    assert (stage.status, stage.attempts, stage.error) == (
        StageStatus.SUCCEEDED,
        2,
        None,
    )


async def test_the_last_attempt_records_the_failure(
    job: ProcessingJob,
    processing_store: InMemoryProcessingStore,
    artifact_storage: InMemoryArtifactStorage,
    decoder: FakeDecoder,
) -> None:
    worker = make_worker(processing_store, artifact_storage, decoder)
    artifact_storage.fail_downloads = 1

    await worker.handle({"job_id": str(job.id)}, receive_count=3)

    [event] = processing_store.events(EventTypes.VAD_FAILED)
    assert event.data["error"].startswith("gave up after 3 attempts")


async def test_redelivered_tasks_for_finished_work_do_nothing(
    job: ProcessingJob,
    processing_store: InMemoryProcessingStore,
    artifact_storage: InMemoryArtifactStorage,
    decoder: FakeDecoder,
) -> None:
    worker = make_worker(processing_store, artifact_storage, decoder)
    await worker.handle({"job_id": str(job.id)}, receive_count=1)

    await worker.handle({"job_id": str(job.id)}, receive_count=2)
    await worker.handle({"job_id": str(uuid.uuid7())}, receive_count=1)

    assert len(processing_store.outbox) == 1
    assert processing_store.jobs[job.id].stage(StageName.VAD).attempts == 1


async def test_storage_is_never_called_inside_a_transaction(
    job: ProcessingJob,
    processing_store: InMemoryProcessingStore,
    artifact_storage: InMemoryArtifactStorage,
    decoder: FakeDecoder,
) -> None:
    def no_open_transaction() -> None:
        assert processing_store.open_transactions == 0, "storage call inside a tx"

    artifact_storage.before_call = no_open_transaction
    worker = make_worker(processing_store, artifact_storage, decoder)

    await worker.handle({"job_id": str(job.id)}, receive_count=1)

    assert processing_store.events(EventTypes.VAD_COMPLETED)


class TimingOutAnalyzer:
    async def analyze(
        self, source: object, target: object, *, max_duration_s: int
    ) -> None:
        raise AnalysisTimedOut("audio analysis exceeded 1800 s")


@pytest.mark.parametrize(("attempt", "retried"), [(1, True), (3, False)])
async def test_analysis_timeouts_are_retried_then_recorded(
    job: ProcessingJob,
    processing_store: InMemoryProcessingStore,
    artifact_storage: InMemoryArtifactStorage,
    attempt: int,
    retried: bool,
) -> None:
    artifact_storage.objects[KEY] = b"original audio bytes"
    worker = VadWorker(
        processing_store.unit_of_work,
        artifact_storage,
        TimingOutAnalyzer(),  # type: ignore[arg-type]
        VadWorkerConfig(params=VadParameters(), max_duration_s=3600, max_attempts=3),
    )

    if retried:
        with pytest.raises(AnalysisTimedOut):
            await worker.handle({"job_id": str(job.id)}, receive_count=attempt)
        assert processing_store.outbox == []
    else:
        await worker.handle({"job_id": str(job.id)}, receive_count=attempt)
        [event] = processing_store.events(EventTypes.VAD_FAILED)
        assert "AnalysisTimedOut: audio analysis exceeded 1800 s" in event.data["error"]
