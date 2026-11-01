"""Readiness checks: technology-agnostic probes, run concurrently under a timeout."""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from audio_platform.core.logging import LogEvent, get_logger

logger = get_logger(__name__)

Probe = Callable[[], Awaitable[None]]  # returns on success, raises on failure


@dataclass(frozen=True, slots=True)
class HealthCheck:
    name: str
    probe: Probe
    required: bool = True  # an optional dependency only degrades readiness


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    ok: bool
    required: bool
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    checks: tuple[CheckResult, ...]

    @property
    def status(self) -> Literal["ok", "degraded", "fail"]:
        if any(not c.ok and c.required for c in self.checks):
            return "fail"
        if any(not c.ok for c in self.checks):
            return "degraded"
        return "ok"


async def _run_one(check: HealthCheck, timeout_s: float) -> CheckResult:
    try:
        async with asyncio.timeout(timeout_s):
            await check.probe()
    except Exception as exc:
        # Only the exception type is exposed: messages may contain hosts or credentials.
        error = "timeout" if isinstance(exc, TimeoutError) else type(exc).__name__
        logger.warning(
            LogEvent.HEALTH_CHECK_FAILED,
            check=check.name,
            required=check.required,
            error=error,
        )
        return CheckResult(check.name, ok=False, required=check.required, error=error)
    return CheckResult(check.name, ok=True, required=check.required)


async def run_checks(
    checks: Sequence[HealthCheck], timeout_s: float
) -> ReadinessReport:
    results = await asyncio.gather(*(_run_one(c, timeout_s) for c in checks))
    return ReadinessReport(checks=tuple(results))
