import json
import uuid
from datetime import UTC, datetime

import httpx

from audio_platform.modules.processing.domain import ProcessingJob, StageName
from tests.fakes.processing import InMemoryArtifactStorage, InMemoryProcessingStore

OWNER = uuid.UUID("00000000-0000-7000-8000-0000000000aa")
USER = {"X-Dev-User-Id": str(OWNER)}
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _job(store: InMemoryProcessingStore) -> ProcessingJob:
    job = ProcessingJob.start(
        job_id=uuid.uuid7(),
        recording_id=uuid.uuid7(),
        owner_id=OWNER,
        object_key="users/a/recordings/r/original",
        now=T0,
    )
    store.jobs[job.id] = job
    return job


async def test_unknown_or_unprocessed_recordings_are_not_found(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get(
        f"/api/v1/recordings/{uuid.uuid7()}/processing", headers=USER
    )
    assert response.status_code == 404


async def test_running_job_shows_its_stage(
    client: httpx.AsyncClient, processing_store: InMemoryProcessingStore
) -> None:
    job = _job(processing_store)
    job.begin_stage(StageName.VAD, now=T0)

    body = (
        await client.get(
            f"/api/v1/recordings/{job.recording_id}/processing", headers=USER
        )
    ).json()

    assert body["status"] == "running"
    assert body["stages"][0] | {"started_at": None} == {
        "name": "vad",
        "status": "running",
        "attempts": 1,
        "error": None,
        "started_at": None,
        "finished_at": None,
    }
    assert body["vad"] is None


async def test_completed_job_includes_the_speech_segments(
    client: httpx.AsyncClient,
    processing_store: InMemoryProcessingStore,
    artifact_storage: InMemoryArtifactStorage,
) -> None:
    job = _job(processing_store)
    job.begin_stage(StageName.VAD, now=T0)
    job.succeed_stage(
        StageName.VAD,
        {
            "speech_detected": True,
            "duration_ms": 2000,
            "speech_ms": 700,
            "speech_ratio": 0.35,
            "segments_key": "users/a/recordings/r/vad.json",
        },
        now=T0,
    )
    job.complete(speech_detected=True, now=T0)
    artifact_storage.objects["users/a/recordings/r/vad.json"] = json.dumps(
        {"segments": [{"start_ms": 290, "end_ms": 990}]}
    ).encode()

    body = (
        await client.get(
            f"/api/v1/recordings/{job.recording_id}/processing", headers=USER
        )
    ).json()

    assert (body["status"], body["speech_detected"]) == ("completed", True)
    assert body["vad"] == {
        "speech_detected": True,
        "duration_ms": 2000,
        "speech_ms": 700,
        "speech_ratio": 0.35,
        "segments": [{"start_ms": 290, "end_ms": 990}],
    }


async def test_other_users_cannot_see_the_job(
    client: httpx.AsyncClient, processing_store: InMemoryProcessingStore
) -> None:
    job = _job(processing_store)
    other = {"X-Dev-User-Id": str(uuid.uuid7())}

    response = await client.get(
        f"/api/v1/recordings/{job.recording_id}/processing", headers=other
    )

    assert response.status_code == 404
