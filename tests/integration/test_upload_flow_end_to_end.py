import os

import httpx
import pytest

from audio_platform.api import create_app
from audio_platform.core.config import Settings

pytestmark = pytest.mark.integration

USER = {"X-Dev-User-Id": "00000000-0000-7000-8000-0000000000aa"}
MIB = 1024 * 1024


async def test_client_uploads_a_recording_through_presigned_urls(
    settings: Settings, s3_endpoint: str
) -> None:
    # A separate signing client, as in docker compose where clients use another host.
    settings = settings.model_copy(
        update={
            "storage": settings.storage.model_copy(
                update={"public_endpoint_url": s3_endpoint}
            )
        }
    )
    audio = os.urandom(5 * MIB + 4096)
    app = create_app(settings)

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as api,
        httpx.AsyncClient() as storage,
    ):
        registered = await api.post(
            "/api/v1/recordings",
            json={
                "filename": "meeting.mp3",
                "content_type": "audio/mpeg",
                "size_bytes": len(audio),
            },
            headers=USER,
        )
        assert registered.status_code == 201, registered.text
        recording_id = registered.json()["recording"]["id"]
        plan = registered.json()["upload"]
        assert plan["part_count"] == 2

        parts = []
        for number in range(1, plan["part_count"] + 1):
            url = (
                await api.post(
                    f"/api/v1/recordings/{recording_id}/parts/{number}/upload-url",
                    headers=USER,
                )
            ).json()["url"]
            start = (number - 1) * plan["part_size_bytes"]
            chunk = audio[start : start + plan["part_size_bytes"]]
            put = await storage.put(url, content=chunk)
            put.raise_for_status()
            parts.append({"part_number": number, "etag": put.headers["etag"]})

        completed = await api.post(
            f"/api/v1/recordings/{recording_id}/complete",
            json={"parts": parts},
            headers=USER,
        )
        assert completed.status_code == 200, completed.text
        assert completed.json()["status"] == "uploaded"

        fetched = await api.get(f"/api/v1/recordings/{recording_id}", headers=USER)
        assert fetched.json()["status"] == "uploaded"
