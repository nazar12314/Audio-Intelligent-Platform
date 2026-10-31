# AWS infrastructure: Mapping architecture ports to AWS services

> [Index](../../README.md) · **Use for:** choosing the managed AWS service for a database/cache/queue/vector store/LLM port. Placeholders are defined in the index.
> **Related:** [03-choosing-infrastructure](../../backend-architecture/03-choosing-infrastructure.md)

## 5. Mapping the architecture's ports to AWS

| Port / component ([architecture §5](../../backend-architecture/03-choosing-infrastructure.md)) | Self-hosted (compose) | AWS default | AWS alternative and when |
|---|---|---|---|
| SQL system of record | PostgreSQL | **RDS for PostgreSQL** (Multi-AZ in prod) | **Aurora PostgreSQL**: faster failover, read replicas at scale, storage autoscaling. **Aurora Serverless v2**: variable or idle load |
| Document store | MongoDB | **MongoDB Atlas on AWS** (via PrivateLink) for full Mongo compatibility | **DocumentDB**: Mongo-API compatible, but check feature and driver compatibility first. **DynamoDB**: access patterns are known up front and key-based ([aws §8.3](../services/data-stores.md)) |
| Cache / sessions / rate limit / locks | Redis | **ElastiCache (Valkey or Redis OSS)**, cluster mode as needed | **ElastiCache Serverless**: unpredictable load. **MemoryDB**: Redis-API data that must be durable |
| Vector store (RAG) | Qdrant / pgvector | **Aurora/RDS PostgreSQL + pgvector**, if Postgres is already in use | **OpenSearch Serverless (vector collections)**: large corpora or hybrid search. **Bedrock Knowledge Bases**: fully managed ingestion and retrieval, at the cost of control |
| Blob store | MinIO / local FS | **S3** ([aws §9](../services/storage.md)) | — |
| Task queue / work distribution | Redis queue / RabbitMQ | **SQS** (+ DLQ) | **Amazon MQ for RabbitMQ**: you need AMQP features or an existing RabbitMQ adapter |
| Pub/sub fan-out | RabbitMQ topic exchange | **SNS → SQS** fan-out | **EventBridge**: content-based routing, cross-account, SaaS events, archive and replay |
| Event streaming (replay, ordering per key) | Kafka | **MSK** (Provisioned or Serverless) when you keep Kafka semantics | **Kinesis Data Streams**: AWS-native streaming with simpler operations ([aws §7.3](../services/messaging-streaming.md)) |
| LLM / embeddings client | Provider API / local model | **Amazon Bedrock** (through a VPC endpoint) | Direct provider APIs via NAT. **SageMaker endpoints**: self-hosted or fine-tuned models |
| Full-text search | Postgres FTS | Postgres FTS | **OpenSearch Service**: relevance tuning, aggregations, log-style search |
| Auth (OIDC provider) | Keycloak | **Cognito user pools** | An existing IdP (Okta, Entra ID, Auth0). The app only validates JWTs via JWKS |
| Email / notifications | SMTP mock | **SES** / **SNS** | — |
| Scheduler | APScheduler / cron | **EventBridge Scheduler** | — |
| Secrets / config | `.env` | **Secrets Manager** (secrets) + **SSM Parameter Store** (config) | — |
| Logs / metrics / traces | stdout / Prometheus / OTel | **CloudWatch Logs / Metrics**, **X-Ray** via the ADOT collector | **Amazon Managed Prometheus + Grafana**: the team already runs Prometheus dashboards |

When a port moves to an AWS-native service, the steps are:

1. Write the new adapter, for example `adapters/sqs.py` next to `adapters/rabbitmq.py`.
2. Run the port's contract tests against it, using LocalStack or moto.
3. Select it in the container through settings, for example
   `<APP>_QUEUE__BACKEND=sqs|rabbitmq`.
