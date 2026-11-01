import argparse
import asyncio
import signal
from typing import cast

from audio_platform.core.config import Settings
from audio_platform.core.container import WorkerRole, build_worker
from audio_platform.core.logging import LogEvent, configure_logging, get_logger
from audio_platform.entrypoints.api import load_settings_or_exit

logger = get_logger(__name__)


async def run(settings: Settings, role: WorkerRole) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    runtime = await build_worker(settings, role)
    async with runtime.resources:
        logger.info(LogEvent.WORKER_STARTED, role=role)
        # Runners finish their current message, then return once `stop` is set.
        async with asyncio.TaskGroup() as group:
            for runner in runtime.runners:
                group.create_task(runner(stop))
    logger.info(LogEvent.WORKER_STOPPED, role=role)


def main() -> None:
    parser = argparse.ArgumentParser(prog="audio-platform-worker")
    parser.add_argument("role", choices=["pipeline", "vad"])
    role = cast(WorkerRole, parser.parse_args().role)
    settings = load_settings_or_exit()
    configure_logging(settings)
    asyncio.run(run(settings, role))


if __name__ == "__main__":
    main()
