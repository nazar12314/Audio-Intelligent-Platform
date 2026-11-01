from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from audio_platform.api.dependencies import ContainerDep
from audio_platform.core.health import ReadinessReport, run_checks

health_router = APIRouter(prefix="/health", tags=["health"])


class LiveOut(BaseModel):
    status: Literal["ok"] = "ok"


class CheckOut(BaseModel):
    status: Literal["ok", "fail"]
    required: bool
    error: str | None = None


class ReadyOut(BaseModel):
    status: Literal["ok", "degraded", "fail"]
    checks: dict[str, CheckOut]

    @classmethod
    def from_report(cls, report: ReadinessReport) -> ReadyOut:
        return cls(
            status=report.status,
            checks={
                c.name: CheckOut(
                    status="ok" if c.ok else "fail", required=c.required, error=c.error
                )
                for c in report.checks
            },
        )


@health_router.get(
    "/live", summary="Process is up (no dependency checks)", response_model=LiveOut
)
async def live() -> LiveOut:
    return LiveOut()


@health_router.get(
    "/ready",
    summary="Required dependencies are reachable",
    response_model=ReadyOut,
    responses={503: {"model": ReadyOut, "description": "A required dependency failed"}},
)
async def ready(container: ContainerDep) -> JSONResponse:
    report = await run_checks(
        container.health_checks, container.settings.health_check_timeout_s
    )
    status_code = 503 if report.status == "fail" else 200
    return JSONResponse(
        ReadyOut.from_report(report).model_dump(), status_code=status_code
    )
