from contextlib import AsyncExitStack
from dataclasses import dataclass
from functools import partial

from audio_platform.core.config import Settings
from audio_platform.core.health import HealthCheck
from audio_platform.infrastructure.db.sql import ping, sql_engine
from audio_platform.infrastructure.storage.s3 import ping_bucket, s3_client


@dataclass(frozen=True, slots=True)
class Container:
    settings: Settings
    resources: (
        AsyncExitStack  # every opened client is registered here and closed on shutdown
    )
    health_checks: tuple[HealthCheck, ...]

    # Feature services are added here


async def build_container(settings: Settings) -> Container:
    stack = AsyncExitStack()
    try:
        engine = await stack.enter_async_context(
            sql_engine(settings.postgres, application_name=settings.service_name)
        )
        s3 = await stack.enter_async_context(s3_client(settings.aws))
    except BaseException:
        await stack.aclose()
        raise

    health_checks = (
        HealthCheck("postgres", partial(ping, engine)),
        HealthCheck("s3", partial(ping_bucket, s3, settings.storage.bucket)),
    )
    return Container(settings=settings, resources=stack, health_checks=health_checks)
