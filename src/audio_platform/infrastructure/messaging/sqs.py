"""SQS publisher and consumer (ElasticMQ locally, Amazon SQS on AWS)."""

import asyncio
import contextlib
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

import aioboto3
import structlog
from aiobotocore.config import AioConfig
from pydantic import ValidationError

from audio_platform.core.config import AwsSettings, MessagingSettings
from audio_platform.core.logging import LogEvent, get_logger
from audio_platform.core.messaging import Event, UnknownDestination

if TYPE_CHECKING:
    from types_aiobotocore_sqs import SQSClient
    from types_aiobotocore_sqs.type_defs import MessageTypeDef

logger = get_logger(__name__)


@asynccontextmanager
async def sqs_client(
    aws: AwsSettings, messaging: MessagingSettings
) -> AsyncIterator[SQSClient]:
    config = AioConfig(
        connect_timeout=aws.connect_timeout_s,
        # Long polls hold the request open for up to wait_time_s.
        read_timeout=messaging.wait_time_s + aws.read_timeout_s,
        retries={"mode": "standard", "max_attempts": aws.max_attempts},
    )
    session = aioboto3.Session(region_name=aws.region)
    async with session.client(
        "sqs", endpoint_url=messaging.endpoint_url, config=config
    ) as client:
        yield client


async def resolve_queue_urls(
    client: SQSClient, queues: Mapping[str, str]
) -> dict[str, str]:
    """Map logical destinations to queue URLs; fails fast if a queue is missing."""
    return {
        destination: (await client.get_queue_url(QueueName=name))["QueueUrl"]
        for destination, name in queues.items()
    }


class SqsPublisher:
    def __init__(self, client: SQSClient, queue_urls: Mapping[str, str]) -> None:
        self._client = client
        self._queue_urls = dict(queue_urls)

    async def publish(self, event: Event, *, destination: str) -> None:
        queue_url = self._queue_urls.get(destination)
        if queue_url is None:
            raise UnknownDestination(destination)
        await self._client.send_message(
            QueueUrl=queue_url,
            MessageBody=event.model_dump_json(),
            MessageAttributes={
                "type": {"DataType": "String", "StringValue": event.type}
            },
        )


@dataclass(frozen=True, slots=True)
class ReceivedEvent:
    event: Event
    receive_count: int  # 1 on first delivery; SQS redelivers until deleted


Handler = Callable[[ReceivedEvent], Awaitable[None]]


class SqsConsumer:
    """
    Deletes a message only after its handler succeeds. A failing handler leaves it
    to reappear after the visibility timeout; the queue's redrive policy moves it
    to the DLQ after too many receives.
    """

    def __init__(
        self,
        client: SQSClient,
        queue_url: str,
        handler: Handler,
        *,
        name: str,
        wait_time_s: int,
        visibility_timeout_s: int,
        handler_timeout_s: float,
    ) -> None:
        self._client = client
        self._queue_url = queue_url
        self._handler = handler
        self._name = name
        self._wait_time_s = wait_time_s
        self._visibility_timeout_s = visibility_timeout_s
        self._handler_timeout_s = handler_timeout_s

    async def run(self, stop: asyncio.Event) -> None:
        """
        On stop, the poll in flight is allowed to finish (at most `wait_time_s`, so
        keep it below the platform's stop grace period) and anything it returns is
        released. Abandoning the poll instead would not help: SQS can still hand
        messages to the closed request, hiding them for a whole lease.
        """
        failures = 0
        while not stop.is_set():
            try:
                response = await self._client.receive_message(
                    QueueUrl=self._queue_url,
                    MaxNumberOfMessages=1,
                    WaitTimeSeconds=self._wait_time_s,
                    VisibilityTimeout=self._visibility_timeout_s,
                    MessageSystemAttributeNames=["ApproximateReceiveCount"],
                )
                failures = 0
            except Exception:
                failures += 1
                logger.exception(LogEvent.CONSUMER_RECEIVE_FAILED, consumer=self._name)
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=min(2**failures, 30))
                continue
            for message in response.get("Messages", []):
                if stop.is_set():
                    await self._release(message)
                else:
                    await self._handle(message)

    async def _release(self, message: MessageTypeDef) -> None:
        """Received while stopping: hand it straight back instead of after the lease."""
        with contextlib.suppress(Exception):
            await self._client.change_message_visibility(
                QueueUrl=self._queue_url,
                ReceiptHandle=message["ReceiptHandle"],
                VisibilityTimeout=0,
            )

    async def _handle(self, message: MessageTypeDef) -> None:
        receipt = message["ReceiptHandle"]
        try:
            event = Event.model_validate_json(message["Body"])
        except ValidationError:
            # Left in the queue: after maxReceiveCount it lands in the DLQ for review.
            logger.error(LogEvent.MESSAGE_INVALID, consumer=self._name)
            return

        receive_count = int(
            message.get("Attributes", {}).get("ApproximateReceiveCount", 1)
        )
        with structlog.contextvars.bound_contextvars(
            request_id=event.correlation_id,
            event_id=str(event.id),
            event_type=event.type,
            consumer=self._name,
        ):
            heartbeat = asyncio.create_task(self._keep_invisible(receipt))
            try:
                async with asyncio.timeout(self._handler_timeout_s):
                    await self._handler(ReceivedEvent(event, receive_count))
            except TimeoutError:
                # Not deleted: it reappears once the lease lapses, then retries or
                # moves to the DLQ like any other failure.
                logger.error(
                    LogEvent.MESSAGE_HANDLING_TIMED_OUT,
                    receive_count=receive_count,
                    timeout_s=self._handler_timeout_s,
                )
                return
            except Exception:
                logger.exception(
                    LogEvent.MESSAGE_HANDLING_FAILED, receive_count=receive_count
                )
                return
            finally:
                heartbeat.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat
            await self._client.delete_message(
                QueueUrl=self._queue_url, ReceiptHandle=receipt
            )

    async def _keep_invisible(self, receipt: str) -> None:
        """Long jobs extend the lease so no other worker picks the message up."""
        while True:
            await asyncio.sleep(self._visibility_timeout_s / 2)
            with contextlib.suppress(Exception):
                await self._client.change_message_visibility(
                    QueueUrl=self._queue_url,
                    ReceiptHandle=receipt,
                    VisibilityTimeout=self._visibility_timeout_s,
                )
