"""
Upload → outbox → SQS → coordinator → VAD worker → ASR worker → job status, on real
Postgres, RustFS and ElasticMQ, with every worker role running in-process. The ASR
worker uses the `tiny` Whisper model (downloaded on the first run).
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from audio_platform.api import create_app
from audio_platform.core.config import AsrSettings, Settings
from audio_platform.core.container import build_worker

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).parents[1] / "fixtures" / "audio"
USER = {"X-Dev-User-Id": "00000000-0000-7000-8000-0000000000e2"}


@pytest.fixture
async def workers(settings: Settings) -> AsyncIterator[None]:
    settings = settings.model_copy(
        update={"asr": AsrSettings(model="tiny", beam_size=1, cpu_threads=2)}
    )
    stop = asyncio.Event()
    async with contextlib.AsyncExitStack() as stack:
        tasks = []
        for role in ("pipeline", "vad", "asr"):
            runtime = await build_worker(settings, role)
            await stack.enter_async_context(runtime.resources)
            tasks += [asyncio.create_task(runner(stop)) for runner in runtime.runners]
        yield
        stop.set()
        await asyncio.gather(*tasks)


@pytest.fixture
async def api(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t"
        ) as client,
    ):
        yield client


async def _upload(
    api: httpx.AsyncClient, data: bytes, filename: str, content_type: str
) -> str:
    registered = (
        await api.post(
            "/api/v1/recordings",
            json={
                "filename": filename,
                "content_type": content_type,
                "size_bytes": len(data),
            },
            headers=USER,
        )
    ).json()
    async with httpx.AsyncClient() as storage:
        put = await storage.put(registered["upload"]["first_part"]["url"], content=data)
        put.raise_for_status()
    recording_id: str = registered["recording"]["id"]
    completed = await api.post(
        f"/api/v1/recordings/{recording_id}/complete",
        json={"parts": [{"part_number": 1, "etag": put.headers["etag"]}]},
        headers=USER,
    )
    assert completed.json()["status"] == "uploaded"
    return recording_id


async def _finished_processing(
    api: httpx.AsyncClient, recording_id: str
) -> dict[str, Any]:
    async with asyncio.timeout(30):
        while True:
            response = await api.get(
                f"/api/v1/recordings/{recording_id}/processing", headers=USER
            )
            if response.status_code == 200 and response.json()["status"] != "running":
                body: dict[str, Any] = response.json()
                return body
            await asyncio.sleep(0.2)


async def test_speech_is_detected_and_transcribed(
    workers: None, api: httpx.AsyncClient
) -> None:
    data = (FIXTURES / "speech_16k_mono.wav").read_bytes()
    recording_id = await _upload(api, data, "speech.wav", "audio/wav")

    result = await _finished_processing(api, recording_id)

    assert (result["status"], result["speech_detected"]) == ("completed", True)
    assert [(s["name"], s["status"]) for s in result["stages"]] == [
        ("vad", "succeeded"),
        ("asr", "succeeded"),
    ]
    assert result["vad"]["segments"]
    assert 8900 <= result["vad"]["duration_ms"] <= 9200
    transcription = result["transcription"]
    assert transcription["language"] == "en"
    assert "audio intelligence platform" in transcription["text"].lower()
    vad_starts = {s["start_ms"] for s in result["vad"]["segments"]}
    vad_ends = {s["end_ms"] for s in result["vad"]["segments"]}
    for segment in transcription["segments"]:
        assert segment["start_ms"] in vad_starts
        assert segment["end_ms"] in vad_ends


async def test_silence_completes_without_speech(
    workers: None, api: httpx.AsyncClient
) -> None:
    data = (FIXTURES / "silence_16k_mono.wav").read_bytes()
    recording_id = await _upload(api, data, "silence.wav", "audio/wav")

    result = await _finished_processing(api, recording_id)

    assert (result["status"], result["speech_detected"]) == ("completed", False)
    assert result["vad"]["segments"] == []
    assert [s["name"] for s in result["stages"]] == ["vad"]
    assert result["transcription"] is None


async def test_files_that_are_not_audio_fail(
    workers: None, api: httpx.AsyncClient
) -> None:
    recording_id = await _upload(
        api, b"not audio at all" * 64, "fake.mp3", "audio/mpeg"
    )

    result = await _finished_processing(api, recording_id)

    assert result["status"] == "failed"
    assert result["failure_reason"].startswith("vad: invalid audio")
    assert result["stages"][0]["attempts"] == 1
