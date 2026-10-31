# AWS infrastructure: Principles and compute choice

> [Index](../../README.md) · **Use for:** first step of any AWS work: ECS/Lambda/EKS/Batch/Glue/SageMaker decision. Placeholders are defined in the index.

> **Verify before relying on a detail.** AWS renames services and changes quotas, limits and prices often; confirm numbers and features against current AWS documentation. Current names: Amazon Data Firehose (was Kinesis Data Firehose), Amazon Managed Service for Apache Flink (was Kinesis Data Analytics), ElastiCache offers Valkey alongside Redis OSS.

## 1. Principles

1. **The app stays cloud-agnostic, and the infrastructure is AWS-specific.**
   - AWS SDK calls appear only in adapters (`infrastructure/aws/…`,
     `modules/<feature>/adapters/<aws_service>.py`).
   - The service must still run locally with `docker compose`, using open-source
     equivalents or LocalStack ([aws §16](../operations/local-dev-and-testing.md)).
2. **Prefer the managed form of the protocol you already use.**
   - Postgres becomes RDS or Aurora PostgreSQL, Redis becomes ElastiCache, RabbitMQ becomes
     Amazon MQ, and Kafka becomes MSK. The adapter code does not change.
   - Adopt an AWS-native service (SQS, DynamoDB, EventBridge) only through a **new adapter
     behind the same port**, and only when it is clearly better in cost, operations, or
     scale.
3. **Everything is infrastructure as code.** Nothing is created by hand in the console,
   except read-only investigation and a break-glass emergency.
4. **Secure by default.**
   - Each environment gets its own account.
   - No long-lived access keys.
   - Least-privilege roles.
   - Private networking for data stores.
   - Encryption everywhere.
5. **Multi-AZ for production, minimal for dev.** The same modules are used for both, with
   different variables.
6. **Cost is a design input.** Tag every resource, set budgets, and pick the cheapest service
   tier that meets the SLO.

---

## 2. Do you need AWS, and which compute?

Decide compute first. It drives networking, deployment, and cost.

| Workload | Default | Choose instead when… |
|---|---|---|
| Containerized HTTP / WebSocket / SSE API (the template's FastAPI app) | **ECS on Fargate** behind an **ALB** | You need a K8s ecosystem or have platform-team standards: **EKS**. You need GPUs, a special kernel, or a very steady load at the lowest cost: **ECS on EC2** (Graviton) |
| Background workers / consumers | **ECS Fargate service**, scaled on queue depth ([aws §7.1](../services/messaging-streaming.md)) | Interruption-tolerant: **Fargate Spot**. Long batch jobs with array or dependency semantics: **AWS Batch** |
| Event glue, light async handlers, cron | **Lambda** + EventBridge / SQS triggers | It runs longer than 15 min, needs heavy dependencies, or keeps persistent connections: use an ECS task |
| Low, spiky traffic HTTP API | **Lambda** + API Gateway HTTP API (or a Function URL) | Responses stream for a long time (LLM): use ALB + ECS ([aws §6.3](../services/networking.md)) |
| Scheduled jobs | **EventBridge Scheduler**, which runs an ECS task or a Lambda | — |
| Static frontend | **S3 + CloudFront** (OAC) | — |
| Big-data transformation | **Glue** (serverless Spark) | You need full Spark control, PB scale, or custom frameworks: **EMR** ([aws §11](../services/data-engineering.md)) |
| ML training / hosting | **SageMaker** ([aws §10](../services/ai-ml.md)) | Managed LLM inference: **Bedrock** |

**Rule:** a single image runs every process type (API, worker, migration). Each ECS service
or task definition picks its process type through `command`. This matches the template's
`entrypoints/`.
