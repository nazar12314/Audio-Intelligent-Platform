import httpx
import pytest
from fastapi import FastAPI

from audio_platform.core.exceptions import ConflictError


@pytest.fixture
def app(app: FastAPI) -> FastAPI:
    async def boom() -> None:
        raise RuntimeError("secret internals")

    async def conflict() -> None:
        raise ConflictError("recording already uploaded")

    async def typed(n: int) -> int:
        return n

    app.add_api_route("/test/boom", boom)
    app.add_api_route("/test/conflict", conflict)
    app.add_api_route("/test/typed", typed)
    return app


async def test_inbound_request_id_is_echoed(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/live", headers={"X-Request-ID": "abc-123"})
    assert response.headers["X-Request-ID"] == "abc-123"


async def test_request_id_is_generated_when_missing_or_malformed(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get(
        "/health/live", headers={"X-Request-ID": "bad id\nwith newline"}
    )
    request_id = response.headers["X-Request-ID"]
    assert (
        request_id and "\n" not in request_id and request_id != "bad id\nwith newline"
    )


async def test_app_error_uses_the_envelope(client: httpx.AsyncClient) -> None:
    response = await client.get("/test/conflict", headers={"X-Request-ID": "req-1"})
    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "conflict",
            "message": "recording already uploaded",
            "request_id": "req-1",
        }
    }


async def test_unknown_route_uses_the_envelope(client: httpx.AsyncClient) -> None:
    response = await client.get("/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_validation_error_uses_the_envelope_without_echoing_input(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/test/typed", params={"n": "not-a-number"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_failed"
    assert "not-a-number" not in response.text
    assert error["details"]["errors"][0]["loc"] == ["query", "n"]


async def test_unhandled_error_returns_generic_500_with_request_id(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/test/boom", headers={"X-Request-ID": "req-500"})
    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "req-500"
    assert response.json()["error"] == {
        "code": "internal_error",
        "message": "Internal server error",
        "request_id": "req-500",
    }
    assert "secret internals" not in response.text
