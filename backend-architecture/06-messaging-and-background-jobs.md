# Backend architecture: Messaging and background jobs

> [Index](../README.md) · **Use for:** events, RabbitMQ, Kafka, outbox, idempotent consumers, DLQs, workers, scheduled/long jobs. Placeholders are defined in the index.
> **Related:** [messaging-streaming](../aws-infrastructure/services/messaging-streaming.md)

## 8. Messaging and asynchronous work

### 8.1 Ports

```python
class EventPublisher(Protocol):
    async def publish(self, event: Event, *, key: str | None = None) -> None: ...

class Event(BaseModel):                 # common envelope for every broker
    id: UUID                            # unique; consumers deduplicate on it
    type: str                           # "<feature>.<entity>.<past_tense_verb>", e.g. "rag.document.uploaded"
    version: int = 1                    # schema version of `data`
    occurred_at: datetime
    correlation_id: str | None          # the request ID that caused it
    data: dict[str, Any]
```

- The services know only `EventPublisher` and the event models. Broker specifics stay in the
  adapters.
- **Consumers are thin**, just like routers. A consumer decodes the envelope, then calls one
  service method, then acks the message.
- The contract for every message is documented in `API.md` (or AsyncAPI): its type, version,
  schema, producer, and consumers.

### 8.2 Delivery guarantees (both brokers)

- Assume **at-least-once** delivery. Every handler must be **idempotent**: deduplicate on
  `event.id` (a Redis `SET NX` with a TTL, or a unique index on the processed-events table),
  or make the operation naturally idempotent (an upsert).
- **Ack or commit after processing**, never before.
- **The transactional outbox**, for events that must not be lost when the database write
  succeeds:
  1. Write the event to an `outbox` table or collection in the same transaction as the state
     change.
  2. A relay task publishes pending outbox rows and marks them as sent.
  3. Do not publish directly after a commit and hope it works.
- **Retries:** bounded, with exponential backoff. After N attempts, send the message to a
  dead-letter queue or topic, with the error attached. A poison message must never block the
  queue.
- **Schema evolution:** only add fields within a version. A breaking change means a new
  `version`, and consumers support both versions during the migration.

### 8.3 RabbitMQ specifics (aio-pika)

- Use one robust connection per process (`connect_robust`), a channel per publisher and per
  consumer, and **publisher confirms** turned on.
- Declare the topology in code and idempotently at startup: exchanges (`topic` by default),
  queues (`durable=True`, quorum queues for important work), bindings, and a dead-letter
  exchange per queue (`x-dead-letter-exchange`).
- Naming: exchange `<app>.<feature>`, routing key = `event.type`, queue
  `<consumer-service>.<feature>.<purpose>`.
- Set the `prefetch_count` explicitly (start at about 10 and tune). Use
  `message.process(requeue=False)` and route failures through the DLX with a retry counter in
  a header.
- Set the heartbeat and the publish timeout explicitly, and log any reconnect.

### 8.4 Kafka specifics (aiokafka)

- Topics are named `<domain>.<entity>.<event>` or `<app>.<feature>.events`. Create them
  explicitly (from the migrate process or an admin script) with an explicit partition count.
  Never rely on auto-create.
- **The partition key** is the entity whose events must stay in order (`conversation_id`,
  `user_id`). Order is guaranteed only within a partition.
- Producer settings: `acks="all"`, `enable_idempotence=True`, compression on.
- Consumer settings: `group_id = "<consumer-service>.<purpose>"`,
  `enable_auto_commit=False`. Commit offsets after a batch has been processed.
- For retries, use retry topics (`<topic>.retry.1`, `.retry.2`, …) and a `.dlq` topic. Never
  block a partition on one bad record.
- Use a schema registry (Avro / Protobuf / JSON Schema) once more than one team or service
  consumes a topic.

### 8.5 Background jobs

- **Fire-and-forget work tied to one request** (sending an email, warming a cache) goes to a
  task queue or an event. It never runs as a bare `asyncio.create_task` inside an API
  process, because that work is lost on restart.
- **Scheduled jobs** run in the worker process (APScheduler, or the queue library's cron).
  When several replicas run the worker, use a distributed lock so a job runs only once.
- **Long-running jobs** (document ingestion, re-indexing) report their progress to a job
  record (`pending → running → succeeded/failed`, plus progress and an error). The API
  returns `202 Accepted` with the job ID, and clients poll or subscribe for updates.
