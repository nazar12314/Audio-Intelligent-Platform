"""Shutdown behaviour of the consumer loop, with a scripted SQS client."""

import asyncio
import time
from typing import Any

from audio_platform.core.messaging import Event
from audio_platform.infrastructure.messaging import ReceivedEvent, SqsConsumer


class ScriptedSqs:
    def __init__(self, *, poll_s: float, on_receive: Any = None) -> None:
        self.poll_s = poll_s
        self.on_receive = on_receive
        self.released: list[str] = []
        self.deleted: list[str] = []

    async def receive_message(self, **_: Any) -> dict[str, Any]:
        await asyncio.sleep(self.poll_s)  # a long poll with nothing arriving
        if self.on_receive is not None:
            self.on_receive()
            return {
                "Messages": [
                    {
                        "ReceiptHandle": "r-1",
                        "Body": Event.new("test.thing.happened", {}).model_dump_json(),
                        "Attributes": {"ApproximateReceiveCount": "1"},
                    }
                ]
            }
        return {}

    async def change_message_visibility(self, **kwargs: Any) -> None:
        if kwargs["VisibilityTimeout"] == 0:
            self.released.append(kwargs["ReceiptHandle"])

    async def delete_message(self, **kwargs: Any) -> None:
        self.deleted.append(kwargs["ReceiptHandle"])


def _consumer(client: ScriptedSqs, handled: list[ReceivedEvent]) -> SqsConsumer:
    async def handler(received: ReceivedEvent) -> None:
        handled.append(received)

    return SqsConsumer(
        client,  # type: ignore[arg-type]
        "queue-url",
        handler,
        name="test",
        wait_time_s=20,
        visibility_timeout_s=60,
        handler_timeout_s=60,
    )


async def test_stop_lets_the_poll_in_flight_finish() -> None:
    stop = asyncio.Event()
    consumer = _consumer(ScriptedSqs(poll_s=0.5), [])
    task = asyncio.create_task(consumer.run(stop))
    await asyncio.sleep(0.1)

    started = time.monotonic()
    stop.set()
    await task

    assert 0.3 < time.monotonic() - started < 2  # the poll completed, nothing more


async def test_messages_received_while_stopping_are_released_not_handled() -> None:
    stop = asyncio.Event()
    client = ScriptedSqs(poll_s=0, on_receive=stop.set)  # stop arrives with the message
    handled: list[ReceivedEvent] = []

    await _consumer(client, handled).run(stop)

    assert handled == []
    assert client.released == ["r-1"]
    assert client.deleted == []
