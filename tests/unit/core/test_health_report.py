import asyncio

from audio_platform.core.health import HealthCheck, run_checks
from tests.conftest import probe_ok, probe_raising


async def test_all_checks_passing_reports_ok() -> None:
    report = await run_checks(
        [HealthCheck("a", probe_ok()), HealthCheck("b", probe_ok())], timeout_s=1
    )
    assert report.status == "ok"


async def test_failing_required_check_reports_fail_with_exception_type_only() -> None:
    report = await run_checks(
        [HealthCheck("db", probe_raising(ConnectionError("db at 10.0.0.5")))],
        timeout_s=1,
    )
    assert report.status == "fail"
    assert report.checks[0].error == "ConnectionError"


async def test_failing_optional_check_reports_degraded() -> None:
    checks = [
        HealthCheck("db", probe_ok()),
        HealthCheck("cache", probe_raising(OSError()), required=False),
    ]
    assert (await run_checks(checks, timeout_s=1)).status == "degraded"


async def test_slow_check_times_out() -> None:
    async def hang() -> None:
        await asyncio.sleep(10)

    report = await run_checks([HealthCheck("slow", hang)], timeout_s=0.01)
    assert report.status == "fail"
    assert report.checks[0].error == "timeout"
