import uuid

import httpx
import pytest

from tests.fakes.recordings import FakeAudioObjectStorage

USER = {"X-Dev-User-Id": "00000000-0000-7000-8000-0000000000aa"}
OTHER_USER = {"X-Dev-User-Id": "00000000-0000-7000-8000-0000000000bb"}
AUDIO = b"RIFF" + b"\x00" * 2044
NEW_RECORDING = {
    "filename": "standup.wav",
    "content_type": "Audio/WAV",
    "size_bytes": len(AUDIO),
}


async def _register(client: httpx.AsyncClient) -> dict[str, object]:
    response = await client.post("/api/v1/recordings", json=NEW_RECORDING, headers=USER)
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


@pytest.mark.parametrize(
    "headers", [{}, {"X-Dev-User-Id": "not-a-uuid"}], ids=["missing", "malformed"]
)
async def test_requests_without_a_valid_user_are_rejected(
    client: httpx.AsyncClient, headers: dict[str, str]
) -> None:
    response = await client.post(
        "/api/v1/recordings", json=NEW_RECORDING, headers=headers
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_register_returns_the_recording_and_its_upload_plan(
    client: httpx.AsyncClient,
) -> None:
    body = await _register(client)

    recording, upload = body["recording"], body["upload"]
    assert isinstance(recording, dict) and isinstance(upload, dict)
    assert recording["status"] == "pending_upload"
    assert recording["content_type"] == "audio/wav"
    assert upload == {
        "part_size_bytes": 16 * 1024 * 1024,
        "part_count": 1,
        "url_ttl_s": 900,
    }
    assert "object_key" not in recording and "upload_id" not in recording


@pytest.mark.parametrize(
    "overrides",
    [
        {"filename": "../etc/passwd"},
        {"filename": "a\nb.wav"},
        {"content_type": "video/mp4"},
        {"size_bytes": 0},
        {"unexpected": "field"},
    ],
)
async def test_invalid_registrations_use_the_error_envelope(
    client: httpx.AsyncClient, overrides: dict[str, object]
) -> None:
    response = await client.post(
        "/api/v1/recordings", json=NEW_RECORDING | overrides, headers=USER
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


async def test_full_upload_flow(
    client: httpx.AsyncClient, fake_storage: FakeAudioObjectStorage
) -> None:
    recording_id = (await _register(client))["recording"]["id"]  # type: ignore[index]

    url_response = await client.post(
        f"/api/v1/recordings/{recording_id}/parts/1/upload-url", headers=USER
    )
    assert url_response.status_code == 200
    etag = fake_storage.put_part(url_response.json()["url"], AUDIO)

    complete = await client.post(
        f"/api/v1/recordings/{recording_id}/complete",
        json={"parts": [{"part_number": 1, "etag": etag}]},
        headers=USER,
    )
    assert complete.status_code == 200, complete.text
    assert complete.json()["status"] == "uploaded"

    fetched = await client.get(f"/api/v1/recordings/{recording_id}", headers=USER)
    assert fetched.json()["status"] == "uploaded"


async def test_other_users_get_not_found(client: httpx.AsyncClient) -> None:
    recording_id = (await _register(client))["recording"]["id"]  # type: ignore[index]

    response = await client.get(
        f"/api/v1/recordings/{recording_id}", headers=OTHER_USER
    )

    assert response.status_code == 404


async def test_abort_then_upload_url_is_a_conflict(client: httpx.AsyncClient) -> None:
    recording_id = (await _register(client))["recording"]["id"]  # type: ignore[index]

    aborted = await client.post(
        f"/api/v1/recordings/{recording_id}/abort", headers=USER
    )
    url_response = await client.post(
        f"/api/v1/recordings/{recording_id}/parts/1/upload-url", headers=USER
    )

    assert aborted.json()["status"] == "aborted"
    assert url_response.status_code == 409


async def test_unknown_recording_is_not_found(client: httpx.AsyncClient) -> None:
    response = await client.get(f"/api/v1/recordings/{uuid.uuid4()}", headers=USER)
    assert response.status_code == 404


async def test_part_number_out_of_range_is_rejected(client: httpx.AsyncClient) -> None:
    recording_id = (await _register(client))["recording"]["id"]  # type: ignore[index]

    for part in (0, 2):
        response = await client.post(
            f"/api/v1/recordings/{recording_id}/parts/{part}/upload-url", headers=USER
        )
        assert response.status_code == 422


async def test_list_and_download_an_uploaded_recording(
    client: httpx.AsyncClient, fake_storage: FakeAudioObjectStorage
) -> None:
    pending = (await _register(client))["recording"]["id"]  # type: ignore[index]
    uploaded = (await _register(client))["recording"]["id"]  # type: ignore[index]
    url = (
        await client.post(
            f"/api/v1/recordings/{uploaded}/parts/1/upload-url", headers=USER
        )
    ).json()["url"]
    etag = fake_storage.put_part(url, AUDIO)
    await client.post(
        f"/api/v1/recordings/{uploaded}/complete",
        json={"parts": [{"part_number": 1, "etag": etag}]},
        headers=USER,
    )

    page = await client.get("/api/v1/recordings", params={"limit": 1}, headers=USER)
    assert [r["id"] for r in page.json()["items"]] == [uploaded]
    next_page = await client.get(
        "/api/v1/recordings",
        params={"limit": 1, "cursor": page.json()["next_cursor"]},
        headers=USER,
    )
    assert [r["id"] for r in next_page.json()["items"]] == [pending]
    assert next_page.json()["next_cursor"] is None

    download = await client.get(
        f"/api/v1/recordings/{uploaded}/download-url", headers=USER
    )
    assert fake_storage.get(download.json()["url"]) == AUDIO
    not_ready = await client.get(
        f"/api/v1/recordings/{pending}/download-url", headers=USER
    )
    assert not_ready.status_code == 409


async def test_list_rejects_bad_limits(client: httpx.AsyncClient) -> None:
    for limit in (0, 101):
        response = await client.get(
            "/api/v1/recordings", params={"limit": limit}, headers=USER
        )
        assert response.status_code == 422
