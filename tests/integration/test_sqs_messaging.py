"""SQS publisher/consumer against ElasticMQ: acks, redelivery, DLQ, lease extension."""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING

import pytest

from audio_platform.core.config import Settings
from audio_platform.core.messaging import Event
from audio_platform.infrastructure.messaging import (
    ReceivedEvent,
    SqsConsumer,
    SqsPublisher,
    sqs_client,
)

if TYPE_CHECKING:
    from types_aiobotocore_sqs import SQSClient

pytestmark = pytest.mark.integration


@pytest.fixture
async def sqs(settings: Settings) -> AsyncIterator[SQSClient]:
    async with sqs_client(settings.aws, settings.messaging) as client:
        yield client


async def _queue(sqs: SQSClient, *, max_receives: int = 5) -> tuple[str, str]:
    name = f"test-{uuid.uuid4().hex[:12]}"
    dlq = (await sqs.create_queue(QueueName=f"{name}-dlq"))["QueueUrl"]
    dlq_arn = (
        await sqs.get_queue_attributes(QueueUrl=dlq, AttributeNames=["QueueArn"])
    )["Attributes"]["QueueArn"]
    redrive = json.dumps(
        {"deadLetterTargetArn": dlq_arn, "maxReceiveCount": max_receives}
    )
    queue = (
        await sqs.create_queue(QueueName=name, Attributes={"RedrivePolicy": redrive})
    )["QueueUrl"]
    return queue, dlq


async def _consume_until(
    sqs: SQSClient,
    queue: str,
    handler: Callable[[ReceivedEvent], Awaitable[None]],
    done: Callable[[], bool],
    *,
    visibility_timeout_s: int = 2,
    timeout_s: float = 20,
) -> None:
    stop = asyncio.Event()
    consumer = SqsConsumer(
        sqs,
        queue,
        handler,
        name="test",
        wait_time_s=1,
        handler_timeout_s=30,
        visibility_timeout_s=visibility_timeout_s,
    )
    task = asyncio.create_task(consumer.run(stop))
    async with asyncio.timeout(timeout_s):
        while not done():
            await asyncio.sleep(0.1)
    stop.set()
    await task


async def _count(sqs: SQSClient, queue: str) -> int:
    attributes = (
        await sqs.get_queue_attributes(
            QueueUrl=queue,
            AttributeNames=[
                "ApproximateNumberOfMessages",
                "ApproximateNumberOfMessagesNotVisible",
            ],
        )
    )["Attributes"]
    return sum(int(v) for v in attributes.values())


async def test_published_events_are_handled_once_and_acknowledged(
    sqs: SQSClient,
) -> None:
    queue, _ = await _queue(sqs)
    event = Event.new("test.thing.happened", {"answer": 42})
    await SqsPublisher(sqs, {"dest": queue}).publish(event, destination="dest")
    received: list[ReceivedEvent] = []

    async def handler(message: ReceivedEvent) -> None:
        received.append(message)

    await _consume_until(sqs, queue, handler, lambda: bool(received))

    assert [(r.event.id, r.event.data, r.receive_count) for r in received] == [
        (event.id, {"answer": 42}, 1)
    ]
    assert await _count(sqs, queue) == 0


async def test_failed_handling_is_redelivered(sqs: SQSClient) -> None:
    queue, _ = await _queue(sqs)
    await SqsPublisher(sqs, {"dest": queue}).publish(
        Event.new("test.thing.happened", {}), destination="dest"
    )
    counts: list[int] = []

    async def flaky(message: ReceivedEvent) -> None:
        counts.append(message.receive_count)
        if message.receive_count == 1:
            raise RuntimeError("transient")

    await _consume_until(
        sqs, queue, flaky, lambda: len(counts) == 2, visibility_timeout_s=1
    )

    assert counts == [1, 2]


async def test_messages_that_keep_failing_end_in_the_dlq(sqs: SQSClient) -> None:
    queue, dlq = await _queue(sqs, max_receives=2)
    await SqsPublisher(sqs, {"dest": queue}).publish(
        Event.new("test.thing.happened", {}), destination="dest"
    )
    attempts: list[int] = []

    async def always_fails(message: ReceivedEvent) -> None:
        attempts.append(message.receive_count)
        raise RuntimeError("poison")

    async def in_dlq() -> bool:
        return await _count(sqs, dlq) == 1

    stop = asyncio.Event()
    consumer = SqsConsumer(
        sqs,
        queue,
        always_fails,
        name="test",
        wait_time_s=1,
        handler_timeout_s=30,
        visibility_timeout_s=1,
    )
    task = asyncio.create_task(consumer.run(stop))
    async with asyncio.timeout(20):
        while not await in_dlq():
            await asyncio.sleep(0.2)
    stop.set()
    await task

    assert attempts == [1, 2]


async def test_long_handling_keeps_the_message_from_other_consumers(
    sqs: SQSClient,
) -> None:
    queue, _ = await _queue(sqs)
    await SqsPublisher(sqs, {"dest": queue}).publish(
        Event.new("test.slow.job", {}), destination="dest"
    )
    handled: list[int] = []

    async def slow(message: ReceivedEvent) -> None:
        handled.append(message.receive_count)
        await asyncio.sleep(3)  # longer than the 2 s visibility timeout

    stop = asyncio.Event()
    consumers = [
        asyncio.create_task(
            SqsConsumer(
                sqs,
                queue,
                slow,
                name=f"c{i}",
                wait_time_s=1,
                handler_timeout_s=30,
                visibility_timeout_s=2,
            ).run(stop)
        )
        for i in range(2)
    ]
    await asyncio.sleep(6)
    stop.set()
    await asyncio.gather(*consumers)

    assert handled == [1]
    assert await _count(sqs, queue) == 0


async def test_handlers_that_overrun_their_time_limit_are_retried(
    sqs: SQSClient,
) -> None:
    queue, _ = await _queue(sqs)
    await SqsPublisher(sqs, {"dest": queue}).publish(
        Event.new("test.hung.job", {}), destination="dest"
    )
    counts: list[int] = []

    async def hangs_first_time(message: ReceivedEvent) -> None:
        counts.append(message.receive_count)
        if message.receive_count == 1:
            await asyncio.sleep(3600)  # stuck: the lease must not be extended forever

    stop = asyncio.Event()
    consumer = SqsConsumer(
        sqs,
        queue,
        hangs_first_time,
        name="test",
        wait_time_s=1,
        visibility_timeout_s=2,
        handler_timeout_s=1,
    )
    task = asyncio.create_task(consumer.run(stop))
    async with asyncio.timeout(20):
        while counts != [1, 2]:
            await asyncio.sleep(0.1)
    stop.set()
    await task

    assert await _count(sqs, queue) == 0
