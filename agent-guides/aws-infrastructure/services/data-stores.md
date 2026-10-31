# AWS infrastructure: Data stores

> [Index](../../README.md) · **Use for:** RDS/Aurora, DocumentDB/Atlas, DynamoDB, ElastiCache, vector search. Placeholders are defined in the index.
> **Related:** [04-database-management](../../backend-architecture/04-database-management.md)

## 8. Data stores

### 8.1 Relational: RDS / Aurora PostgreSQL

- **Placement:** `private-data` subnets only.
- **Availability and backups:**
  - **Multi-AZ** in prod.
  - Automated backups with a retention of 7–35 days, and **PITR** on.
  - Deletion protection on.
- **Encryption:**
  - At rest with KMS.
  - TLS enforced (`rds.force_ssl=1`).
  - The master password managed by RDS in Secrets Manager.
- **Connections:**
  - The app connects with a least-privilege role, never as the master user.
  - Size the SQLAlchemy pool per task × the task count, and keep the total below
    `max_connections`.
  - **RDS Proxy** pools connections for Lambda or for many small tasks.
- **Operations:**
  - Read replicas (or Aurora readers) for read scaling. Route reads explicitly in the
    adapter.
  - Turn on Performance Insights and Enhanced Monitoring in prod.
  - Change parameters through custom parameter groups in IaC.
- **Migrations run as a one-off ECS task** using the new image, before the service updates
  ([aws §14](../operations/cicd-deployment.md)).

### 8.2 Document: Atlas / DocumentDB

- **Atlas on AWS:** connect through **PrivateLink**, put the credentials in Secrets Manager,
  and keep the same driver and adapter.
- **DocumentDB** is MongoDB-*compatible*, not MongoDB. Check the operators, indexes,
  transactions, and change streams the app uses against the compatibility list. Enforce TLS
  with the AWS CA bundle. Its storage and cluster model is Aurora-like.

### 8.3 DynamoDB: when access patterns are known

- **Use it for** key-value or single-table designs with known queries, millisecond latency at
  any scale, serverless operation, TTL expiry, and change streams. Good fits include sessions,
  idempotency keys, rate-limit counters, job status, and user preferences.
- **Avoid it for** ad-hoc queries, joins, reporting, or access patterns that change often.
  Use Postgres for those.
- Design the keys from the access patterns first, and document them in an ADR. Use **on-demand
  capacity** by default and provisioned capacity with autoscaling for steady load. Turn on
  **PITR**. Use **TTL** for expiry.

### 8.4 ElastiCache (Valkey / Redis OSS)

- Encrypt in transit (TLS) and at rest, and use **AUTH / RBAC users**. Clients connect with
  `rediss://`.
- Prod uses replicas with automatic failover across AZs. Use cluster mode only when one shard
  is not enough, and keep in mind that it constrains multi-key operations to one hash slot.
- It remains **non-authoritative** data, as [architecture §6.4](../../backend-architecture/04-database-management.md) requires. Losing the
  cache must never lose business data.

### 8.5 Vector search for RAG

| Situation | Pick |
|---|---|
| Postgres is already in use, the corpus is up to a few million vectors, and filtering is simple | **pgvector** on RDS or Aurora (HNSW index) |
| Large corpus, hybrid keyword + vector search, heavy metadata filters | **OpenSearch Serverless** vector collection (or OpenSearch Service) |
| You want ingestion, chunking, embedding, and retrieval managed, and accept less control | **Bedrock Knowledge Bases**, with S3 as the source |

The owner or tenant filter must be **inside** the vector query, whatever the backend.
