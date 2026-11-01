import uuid

import pytest

from audio_platform.modules.processing.domain import JobStatus
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


@pytest.mark.parametrize("speech", [True, False])
async def test_vad_completion_completes_the_job(
    coordinator: PipelineCoordinator,
    processing_store: InMemoryProcessingStore,
    speech: bool,
) -> None:
    job_id = await _start(coordinator, processing_store)

    await coordinator.vad_completed({"job_id": job_id, "speech_detected": speech})
    await coordinator.vad_completed({"job_id": job_id, "speech_detected": not speech})

    job = processing_store.jobs[uuid.UUID(job_id)]
    assert (job.status, job.speech_detected) == (JobStatus.COMPLETED, speech)


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
