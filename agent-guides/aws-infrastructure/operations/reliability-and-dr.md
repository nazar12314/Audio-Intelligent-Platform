# AWS infrastructure: Reliability, backups, disaster recovery

> [Index](../../README.md) · **Use for:** RTO/RPO, Multi-AZ, AWS Backup, restore drills, quotas. Placeholders are defined in the index.

## 15. Reliability, backups, disaster recovery

- **Define the RTO and RPO per environment first.** They decide the architecture:

  | Target | Typical setup |
  |---|---|
  | Hours / 24 h | Backups only (single region, Multi-AZ) |
  | Minutes | Multi-AZ, plus a warm standby or pilot light in a second region with replicated data |
  | Near zero | Active-active multi-region (expensive; justify it in an ADR) |

- **Multi-AZ everywhere in prod:** ECS tasks spread across AZs, RDS Multi-AZ, ElastiCache
  replicas, NAT per AZ.
- **AWS Backup** plans for RDS, DynamoDB, EFS, and EBS, with retention per policy and a
  **cross-region and/or cross-account copy** for prod. S3 uses versioning, plus replication
  (CRR) where required.
- **Restores are tested on a schedule.** A backup that has never been restored does not
  count.
- **Avoid single points of failure:** no singleton EC2 instances, no single-AZ data stores in
  prod, no manual-only resources.
- Use idempotent consumers, DLQs, and retries ([architecture §8](../../backend-architecture/06-messaging-and-background-jobs.md)) so that transient
  AWS faults recover on their own.
- **Plan quotas** (service quotas: ENIs, Fargate vCPU, Bedrock TPM/RPM, Lambda concurrency)
  before launch, with alarms on usage.
