# AWS infrastructure: Cost management

> [Index](../../README.md) · **Use for:** budgets, Graviton, Spot, Savings Plans, NAT/endpoint costs, lifecycle, LLM cost. Placeholders are defined in the index.

## 17. Cost management

- **Visibility:**
  - Activate the mandatory tags as cost allocation tags.
  - Set up **AWS Budgets**, with alerts at 50/80/100%, per account.
  - Turn on Cost Anomaly Detection.
  - Do a monthly review in Cost Explorer.
- **Compute:**
  - Use **Graviton (arm64)** for Fargate, EC2, Lambda, RDS, and ElastiCache. Build arm64 or
    multi-arch images.
  - Use **Fargate Spot** or EC2 Spot for workers that tolerate interruption, and for EMR task
    nodes.
  - Buy **Savings Plans** or reservations for steady production baselines.
  - Scale dev to zero outside working hours (scheduled scaling).
- **Network:**
  - NAT gateway data processing is a classic surprise cost. Add the S3 and DynamoDB gateway
    endpoints and the interface endpoints for chatty services.
  - Use one NAT gateway in dev.
  - Keep traffic within an AZ where possible.
- **Storage and data:**
  - S3 lifecycle rules and Intelligent-Tiering ([aws §9.2](../services/storage.md)).
  - Log retention set on every log group.
  - Athena on Parquet with partitions (you pay per byte scanned).
  - Delete old ECR images with a lifecycle policy: keep the last N, and expire untagged
    images.
- **Databases:**
  - Right-size the instances.
  - Use Aurora Serverless v2, DynamoDB on-demand, or ElastiCache Serverless for spiky or
    idle workloads.
  - Turn off Multi-AZ in dev.
- **LLM:**
  - Cache deterministic results ([architecture §7.1](../../backend-architecture/05-caching-and-sessions.md)).
  - Choose the smallest model that meets the quality bar.
  - Set per-user quotas.
  - Track cost per request in metrics.
