# AWS infrastructure: Messaging and streaming

> [Index](../../README.md) · **Use for:** SQS, SNS, EventBridge, Kinesis, MSK, Firehose, Flink, Amazon MQ. Placeholders are defined in the index.
> **Related:** [06-messaging-and-background-jobs](../../backend-architecture/06-messaging-and-background-jobs.md)

## 7. Messaging and streaming: when to use which

### 7.1 SQS: work queues (the default for asynchronous work)

- **Standard queues** give at-least-once delivery with best-effort ordering, at nearly
  unlimited scale. **FIFO queues** give ordering per `MessageGroupId` and deduplication, with
  lower throughput. Use FIFO only when order matters within a key.
- **The visibility timeout must exceed the worst-case processing time.** For Lambda triggers,
  follow the AWS guidance of about 6× the function timeout.
- **Every queue has a DLQ**, with `maxReceiveCount` between 3 and 5. Alarm when the DLQ holds
  more than 0 messages. Use **redrive** to replay messages after a fix.
- Use long polling (`WaitTimeSeconds=20`). Use batch send and receive.
- Large payloads use the **claim-check pattern**: store the body in S3, and send only the S3
  key in the message.
- Scale workers on **backlog per task** (`ApproximateNumberOfMessagesVisible` ÷ running
  tasks) with target tracking. Let it scale to 0 in dev if a cold start is acceptable.
- The handlers stay idempotent, exactly as [architecture §8.2](../../backend-architecture/06-messaging-and-background-jobs.md) requires.

### 7.2 SNS and EventBridge: fan-out and routing

- **SNS → several SQS queues** is the standard fan-out: one event, several independent
  consumers, each with its own queue and DLQ. Use subscription filter policies for routing.
- **EventBridge** suits domain events between services or accounts. It adds rules with
  content-based filtering, a schema registry, **archive and replay**, and SaaS and AWS-service
  events as sources. It has higher latency than SNS, which is fine for business events.

### 7.3 Kinesis versus SQS versus MSK

| Question | Answer |
|---|---|
| One application processes tasks, and a message is gone once handled | **SQS** |
| **Several applications must read the same data**, with replay within a retention window, and order per key | **Kinesis Data Streams** (retention is 24 h by default, extendable up to 365 days) |
| You already use Kafka, need the Kafka API or ecosystem (Connect, Streams), or must be portable | **MSK** (Serverless for variable load, Provisioned for steady or high throughput) |
| The simplest way to land streaming data in S3, Redshift, or OpenSearch | **Amazon Data Firehose**: fully managed, batches, compresses, and can transform with Lambda. It is **near-real-time**: it buffers by time or size, whichever limit comes first |
| Real-time transformation or analytics on a stream (windows, joins, event time) | **Managed Service for Apache Flink** |
| Live video or audio ingestion | **Kinesis Video Streams** |

Kinesis Data Streams capacity:

- **Provisioned mode:** each shard handles 1 MB/s (or 1,000 records/s) of writes and
  2 MB/s of reads. To scale, add shards (resharding).
- **On-demand mode:** capacity is managed for you. It costs more when the load is steady.
- **Partition key:** use the entity whose events must stay ordered, as with Kafka.

### 7.4 Amazon MQ

Use it **only** to keep an existing RabbitMQ or ActiveMQ integration unchanged (AMQP,
exchanges, existing adapters). For new designs on AWS, prefer SQS plus SNS or EventBridge,
which are serverless and need no broker to size or patch.
