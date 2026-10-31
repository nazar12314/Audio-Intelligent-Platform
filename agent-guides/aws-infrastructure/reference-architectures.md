# AWS infrastructure: Reference architectures

> [Index](../README.md) · **Use for:** starting point diagrams: container API + workers, LLM chatbot, data/ML pipeline. Placeholders are defined in the index.

## 18. Reference architectures

### 18.1 Containerized API with workers (the most common baseline)

```
Route 53 ─► (CloudFront) ─► WAF ─► ALB [public subnets, 443]
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
          ECS Fargate: api (≥2 tasks, multi-AZ)   ECS Fargate: worker (scales on SQS backlog)
          [private-app subnets]                   [private-app subnets]
                    │        ╲                 ╱        │
                    ▼         ▼               ▼         ▼
     RDS PostgreSQL     ElastiCache        SQS (+DLQ) ◄── SNS/EventBridge
     Multi-AZ           (Valkey/Redis)                     S3 (presigned uploads, events → SQS)
     [private-data]     [private-data]
  Secrets Manager / SSM ─► task definitions     CloudWatch Logs/Metrics, X-Ray, alarms ─► SNS
  ECR (immutable SHA tags)   VPC endpoints: S3, ECR, Logs, Secrets, SQS   one-off ECS task: migrations
```

### 18.2 LLM chatbot backend

This is 18.1 plus the following:

- **LLM and embeddings:**
  - **Bedrock** through a VPC endpoint, behind the `LLMClient` / `EmbeddingClient` adapters.
  - The model IDs live in SSM or env vars.
  - Guardrails are optional.
- **Streaming:**
  - **ALB → ECS** for SSE token streaming.
  - Set the ALB idle timeout and the ECS `stopTimeout` / deregistration delay to cover the
    longest stream.
- **Document ingestion:**
  1. The client uploads with an S3 presigned URL.
  2. An S3 event goes to SQS.
  3. The **ingestion worker** (ECS, Fargate Spot is acceptable) parses, chunks, embeds, and
     upserts the vectors.
  4. It records the job status (RDS or DynamoDB).
  5. A failed message goes to the DLQ, which raises an alarm.
- **Vectors:**
  - **pgvector** on the same RDS/Aurora instance to start.
  - **OpenSearch Serverless** when the corpus or the filtering needs grow.
  - Alternatively, **Bedrock Knowledge Bases** if managed RAG is acceptable.
- **Sessions, cache, rate limits, idempotency keys:** ElastiCache. Use DynamoDB instead when
  the project wants serverless key-value storage with TTL.
- **Conversations:**
  - RDS PostgreSQL by default.
  - Atlas (PrivateLink) or DocumentDB if the architecture ADR chose a document store.
  - DynamoDB if the access patterns are strictly per conversation and per user.
- **Auth:**
  - The app's own JWT auth, with signing keys in Secrets Manager.
  - Or **Cognito** / an external IdP, with the app validating JWTs through JWKS.
- **WAF:** rate-based rules on `/auth/*` and on the chat endpoints. Bedrock quotas are raised
  before launch.

### 18.3 Data / ML pipeline

```
Sources ─► (DMS CDC | Kinesis/MSK | batch uploads) ─► S3 raw
        ─► Glue crawler + ETL (bookmarks) ─► S3 curated (Parquet, partitioned) ─► Glue Catalog
        ─► Athena / Redshift (+Spectrum) / QuickSight
        ─► SageMaker Pipelines: process ─► train (Pipe/FastFile; FSx/EFS) ─► evaluate ─► Model Registry
        ─► real-time | serverless | async endpoint (production variants) or Batch Transform ─► Model Monitor
Lifecycle: raw ─► IA (30d) ─► Glacier (90d+)
```
