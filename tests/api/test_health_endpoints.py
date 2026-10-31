import httpx
import pytest

from audio_platform.core.health import HealthCheck
from tests.conftest import probe_ok, probe_raising


async def test_live_returns_ok_without_checking_dependencies(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


class TestReadyAllHealthy:
    @pytest.fixture
    def health_checks(self) -> list[HealthCheck]:
        return [HealthCheck("postgres", probe_ok()), HealthCheck("s3", probe_ok())]

    async def test_ready_returns_200(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/health/ready")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert set(response.json()["checks"]) == {"postgres", "s3"}


class TestReadyRequiredDependencyDown:
    @pytest.fixture
    def health_checks(self) -> list[HealthCheck]:
        return [HealthCheck("postgres", probe_raising(ConnectionRefusedError())), HealthCheck("s3", probe_ok())]

    async def test_ready_returns_503_with_details(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/health/ready")
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "fail"
        assert body["checks"]["postgres"] == {"status": "fail", "required": True, "error": "ConnectionRefusedError"}


class TestReadyOptionalDependencyDown:
    @pytest.fixture
    def health_checks(self) -> list[HealthCheck]:
        return [HealthCheck("postgres", probe_ok()), HealthCheck("cache", probe_raising(OSError()), required=False)]

    async def test_ready_stays_200_but_degraded(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/health/ready")
        assert response.status_code == 200
        assert response.json()["status"] == "degraded"
