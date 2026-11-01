"""Thin message handlers: decode the envelope, call one service method."""

from audio_platform.core.logging import get_logger
from audio_platform.infrastructure.messaging import ReceivedEvent
from audio_platform.modules.processing.services import (
    EventTypes,
    PipelineCoordinator,
    VadWorker,
)

logger = get_logger(__name__)


class PipelineEventsConsumer:
    def __init__(self, coordinator: PipelineCoordinator) -> None:
        self._coordinator = coordinator

    async def __call__(self, received: ReceivedEvent) -> None:
        event = received.event
        match event.type:
            case EventTypes.RECORDING_UPLOADED:
                await self._coordinator.recording_uploaded(event.data)
            case EventTypes.VAD_COMPLETED:
                await self._coordinator.vad_completed(event.data)
            case EventTypes.VAD_FAILED:
                await self._coordinator.vad_failed(event.data)
            case _:
                logger.warning("messaging.message.ignored", event_type=event.type)


class VadTasksConsumer:
    def __init__(self, worker: VadWorker) -> None:
        self._worker = worker

    async def __call__(self, received: ReceivedEvent) -> None:
        if received.event.type != EventTypes.VAD_REQUESTED:
            logger.warning("messaging.message.ignored", event_type=received.event.type)
            return
        await self._worker.handle(
            received.event.data, receive_count=received.receive_count
        )
