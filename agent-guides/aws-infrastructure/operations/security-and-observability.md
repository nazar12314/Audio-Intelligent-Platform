# AWS infrastructure: Security and observability

> [Index](../../README.md) · **Use for:** CloudTrail/GuardDuty/Security Hub/Config, IAM practice, CloudWatch logs/metrics/alarms, X-Ray. Placeholders are defined in the index.
> **Related:** [10-observability](../../backend-architecture/10-observability.md)

## 13. Security and observability baseline

### 13.1 Security services (enable organization-wide, in every account)

| Service | Purpose |
|---|---|
| **CloudTrail** (org trail, to the log-archive account, with log file validation) | Audit of every API call |
| **GuardDuty** | Threat detection |
| **Security Hub** (with the AWS Foundational Best Practices standard) | Posture findings in one place |
| **AWS Config** (conformance packs) | Configuration compliance |
| **IAM Access Analyzer** | Detects unintended external access and unused permissions |
| **Inspector** | Scans ECR images and Lambda functions for vulnerabilities |
| **Budgets / Cost Anomaly Detection** | Cost alarms ([aws §17](cost.md)) |

**IAM practice:**

- Write one policy per workload role, with explicit actions on explicit resource ARNs. Avoid
  `*` on resources or actions, except where the service requires it.
- Use conditions (`aws:SourceVpce`, `aws:PrincipalOrgID`) on bucket and queue policies.
- Lambdas in a VPC and ECS tasks run in private subnets. EC2 enforces **IMDSv2**.
- Containers run as a non-root user with a read-only root file system where possible. ECR has
  **immutable tags** and scan-on-push turned on.

### 13.2 Observability

- **Logs:**
  - The app writes JSON to stdout (as the template does), sent to **CloudWatch Logs** by the
    `awslogs` driver, or by FireLens for routing elsewhere.
  - Each service gets its own log group, with **retention set** (14–30 days in dev, by
    policy in prod; never "never expire").
  - Query by `request_id` with Logs Insights.
- **Metrics:**
  - CloudWatch container metrics (Container Insights) and ALB, RDS, SQS, and ElastiCache
    metrics.
  - App metrics as Prometheus (scraped by ADOT into AMP) or as CloudWatch EMF.
- **Traces:** OpenTelemetry in the app (template) sends to the **ADOT** collector sidecar,
  which forwards to **X-Ray** (or another OTLP backend).
- **Alarms** go to SNS, then to chat or paging. At minimum alarm on:
  - ALB 5xx rate and target p95/p99 latency;
  - unhealthy targets;
  - ECS tasks below the desired count;
  - RDS CPU, free storage, connections, and replica lag;
  - SQS oldest-message age **and DLQ above 0**;
  - ElastiCache memory and evictions;
  - Lambda errors and throttles;
  - budget thresholds.
- **Dashboards:** one CloudWatch dashboard per service and environment, defined in IaC.
