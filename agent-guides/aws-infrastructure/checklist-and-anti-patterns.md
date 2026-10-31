# AWS infrastructure: Checklist and anti-patterns

> [Index](../README.md) · **Use for:** adding AWS to a project end to end; reviewing an AWS design. Placeholders are defined in the index.

## 19. Checklist: adding AWS to a project

1. Write an ADR covering the compute choice ([aws §2](foundation/01-principles-and-compute.md)), the managed service for each port ([aws §5](foundation/04-service-mapping.md)),
   the region, and the RTO/RPO ([aws §15](operations/reliability-and-dr.md)).
2. Bootstrap each account: an Identity Center permission set, the state bucket, the CI OIDC
   provider, and the per-environment deploy roles. Turn on the org security services ([aws §13.1](operations/security-and-observability.md)).
3. Create `infra/` with modules and environments ([aws §4](foundation/03-infrastructure-as-code.md)). Run `fmt`, `validate`, `tflint`, and
   `checkov` in pre-commit and CI.
4. Create the network module: VPC, three subnet tiers, NAT, endpoints, flow logs ([aws §6](services/networking.md)).
5. Create the data stores the ADR selected, with encryption, backups, deletion protection,
   private subnets, and alarms ([aws §8](services/data-stores.md)–[aws §9](services/storage.md)).
6. Create the messaging resources, each queue with its DLQ and alarms ([aws §7](services/messaging-streaming.md)).
7. Create the ECR repo (immutable tags, scan on push, lifecycle policy), the ECS cluster, the
   services, and the ALB with TLS and WAF ([aws §6.2](services/networking.md), [aws §14](operations/cicd-deployment.md)).
8. Create the secrets and parameters, wired into the task definitions as the env vars the app
   reads ([aws §12](operations/secrets-and-config.md)).
9. Build observability: log groups with retention, dashboards, alarms to SNS, and the ADOT
   collector ([aws §13.2](operations/security-and-observability.md)).
10. Build the CI/CD pipeline: build once, migration task, circuit breaker or blue/green,
    promote the digest, prod approval ([aws §14](operations/cicd-deployment.md)).
11. Build cost controls: tags, budgets, anomaly detection, Graviton, Spot for workers, and
    dev scale-to-zero ([aws §17](operations/cost.md)).
12. Add LocalStack and moto tests for each AWS adapter ([aws §16](operations/local-dev-and-testing.md)).
13. Verify:
    - `terraform plan` is clean in every environment;
    - the dev deploy is green, and the smoke test against `/health/ready` passes;
    - a restore drill succeeds;
    - the DLQ alarm fires on a poison message;
    - the security findings are triaged.

---

## 20. Anti-patterns

| Anti-pattern | Do instead |
|---|---|
| Resources created in the console | IaC only; imports for legacy resources |
| One account for every environment | A separate prod account at minimum |
| IAM users with access keys, for people or CI | Identity Center for people, OIDC and roles for CI, task roles for workloads |
| `"Resource": "*"` / `"Action": "*"` policies | Specific actions on specific ARNs |
| Databases in public subnets, or SGs open to `0.0.0.0/0` | Private-data subnets, with SG-to-SG rules |
| Secrets in env files baked into images, in plain task env, or in TF state | Secrets Manager referenced through `secrets` / `valueFrom` |
| AWS SDK calls scattered through services | AWS code inside adapters, behind ports |
| Rebuilding the image per environment; mutable `latest` tags | Build once, promote the immutable digest |
| Migrations run at app startup across N tasks | A one-off migration task before the service update |
| SQS queue without a DLQ; visibility timeout shorter than processing time | A DLQ with alarms, and a visibility timeout above the processing time |
| SQS where several consumers must read the same data | Kinesis, MSK, or SNS fan-out to multiple queues |
| Firehose where true real-time processing is required | Kinesis Data Streams + Flink or consumers |
| API Gateway in front of long LLM streams | ALB → ECS with a tuned idle timeout |
| Large uploads through the API | S3 presigned URLs and S3 events |
| No log retention; no budgets; NAT carrying all S3 traffic | Retention policy, budgets and alerts, gateway endpoints |
| Single-AZ prod; backups never restored | Multi-AZ, plus scheduled restore drills |
| A long-running EMR cluster for a nightly job | A transient cluster or EMR Serverless, with Spot task nodes |
| Querying raw CSV/JSON in Athena at scale | Parquet, partitioned and compacted |
| Everything kept in S3 Standard forever | Lifecycle rules or Intelligent-Tiering |
