import uuid

import pytest

from audio_platform.modules.processing.domain import JobStatus, StageName, StageStatus
from audio_platform.modules.processing.services import EventTypes, PipelineCoordinator
from tests.fakes.processing import InMemoryProcessingStore

RECORDING = {
    "recording_id": str(uuid.uuid7()),
    "owner_id": str(uuid.uuid7()),
    "object_key": "users/u/recordings/r/original",
}


@pytest.fixture
def coordinator(processing_store: InMemoryProcessingStore) -> PipelineCoordinator:
    return PipelineCoordinator(processing_store.unit_of_work)


async def _start(
    coordinator: PipelineCoordinator, store: InMemoryProcessingStore
) -> str:
    await coordinator.recording_uploaded(RECORDING)
    return str(next(iter(store.jobs)))


async def test_upload_starts_a_job_and_requests_vad(
    coordinator: PipelineCoordinator, processing_store: InMemoryProcessingStore
) -> None:
    job_id = await _start(coordinator, processing_store)

    job = processing_store.jobs[uuid.UUID(job_id)]
    assert (job.status, str(job.recording_id)) == (
        JobStatus.RUNNING,
        RECORDING["recording_id"],
    )
    [(destination, event)] = processing_store.outbox
    assert (destination, event.type, event.data) == (
        "vad-tasks",
        EventTypes.VAD_REQUESTED,
        {"job_id": job_id},
    )


async def test_a_redelivered_upload_event_starts_nothing_new(
    coordinator: PipelineCoordinator, processing_store: InMemoryProcessingStore
) -> None:
    await coordinator.recording_uploaded(RECORDING)
    await coordinator.recording_uploaded(RECORDING)

    assert len(processing_store.jobs) == 1
    assert len(processing_store.outbox) == 1


async def test_silence_completes_the_job_after_vad(
    coordinator: PipelineCoordinator, processing_store: InMemoryProcessingStore
) -> None:
    job_id = await _start(coordinator, processing_store)

    await coordinator.vad_completed({"job_id": job_id, "speech_detected": False})
    await coordinator.vad_completed({"job_id": job_id, "speech_detected": True})

    job = processing_store.jobs[uuid.UUID(job_id)]
    assert (job.status, job.speech_detected) == (JobStatus.COMPLETED, False)
    assert list(job.stages) == [StageName.VAD]
    assert processing_store.events(EventTypes.ASR_REQUESTED) == []


async def test_speech_requests_transcription_once(
    coordinator: PipelineCoordinator, processing_store: InMemoryProcessingStore
) -> None:
    job_id = await _start(coordinator, processing_store)

    await coordinator.vad_completed({"job_id": job_id, "speech_detected": True})
    await coordinator.vad_completed({"job_id": job_id, "speech_detected": True})

    job = processing_store.jobs[uuid.UUID(job_id)]
    assert (job.status, job.speech_detected) == (JobStatus.RUNNING, True)
    assert job.stage(StageName.ASR).status is StageStatus.PENDING
    destination, event = processing_store.outbox[-1]
    assert (destination, event.type, event.data) == (
        "asr-tasks",
        EventTypes.ASR_REQUESTED,
        {"job_id": job_id},
    )
    assert len(processing_store.events(EventTypes.ASR_REQUESTED)) == 1


async def test_transcription_completes_the_job(
    coordinator: PipelineCoordinator, processing_store: InMemoryProcessingStore
) -> None:
    job_id = await _start(coordinator, processing_store)
    await coordinator.vad_completed({"job_id": job_id, "speech_detected": True})

    await coordinator.asr_completed({"job_id": job_id, "language": "en"})
    await coordinator.asr_failed({"job_id": job_id, "error": "late duplicate"})

    job = processing_store.jobs[uuid.UUID(job_id)]
    assert (job.status, job.speech_detected) == (JobStatus.COMPLETED, True)


async def test_transcription_failure_fails_the_job(
    coordinator: PipelineCoordinator, processing_store: InMemoryProcessingStore
) -> None:
    job_id = await _start(coordinator, processing_store)
    await coordinator.vad_completed({"job_id": job_id, "speech_detected": True})

    await coordinator.asr_failed({"job_id": job_id, "error": "gave up"})

    job = processing_store.jobs[uuid.UUID(job_id)]
    assert (job.status, job.failure_reason) == (JobStatus.FAILED, "asr: gave up")


async def test_vad_failure_fails_the_job(
    coordinator: PipelineCoordinator, processing_store: InMemoryProcessingStore
) -> None:
    job_id = await _start(coordinator, processing_store)

    await coordinator.vad_failed(
        {"job_id": job_id, "error": "invalid audio: no audio stream"}
    )

    job = processing_store.jobs[uuid.UUID(job_id)]
    assert job.status is JobStatus.FAILED
    assert job.failure_reason == "vad: invalid audio: no audio stream"


async def test_events_for_unknown_jobs_are_ignored(
    coordinator: PipelineCoordinator,
) -> None:
    await coordinator.vad_completed(
        {"job_id": str(uuid.uuid7()), "speech_detected": True}
    )
    await coordinator.vad_failed({"job_id": str(uuid.uuid7()), "error": "x"})
    await coordinator.asr_completed({"job_id": str(uuid.uuid7()), "language": "en"})
    await coordinator.asr_failed({"job_id": str(uuid.uuid7()), "error": "x"})
