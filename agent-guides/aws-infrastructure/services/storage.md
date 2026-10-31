# AWS infrastructure: Storage

> [Index](../../README.md) · **Use for:** S3 baseline, storage classes and lifecycle, EBS/EFS/FSx. Placeholders are defined in the index.

## 9. Storage

### 9.1 S3 baseline (`modules/s3-bucket`)

- Block Public Access at the account level **and** on each bucket. Object ownership is
  *bucket owner enforced*, so ACLs are off.
- **Encryption:**
  - Default encryption is on: SSE-S3, or **SSE-KMS** with a bucket key for regulated data.
  - The bucket policy denies requests where `aws:SecureTransport = false`.
- **Versioning** is on for anything that cannot be recreated. Lifecycle rules expire
  noncurrent versions and abort incomplete multipart uploads after 7 days.
- **Uploads from clients** use **presigned URLs** (PUT, or POST with conditions on size and
  content type). Large files never pass through the API.
- **S3 events** go to SQS (or EventBridge) to start processing. Never poll a bucket.
- **Layout:** one bucket per purpose and environment (`<project>-<env>-uploads`,
  `-artifacts`, `-datalake-raw`). Use prefixes for partitions (`dt=YYYY-MM-DD/`).

### 9.2 Storage classes: when to use each

| Class | Use for | Access | AZs | Note |
|---|---|---|---|---|
| **S3 Standard** | Active, frequently accessed data | ms | ≥ 3 | Default |
| **S3 Intelligent-Tiering** | **Unknown or changing** access patterns | ms | ≥ 3 | Small per-object monitoring fee; objects under 128 KB are not auto-tiered |
| **S3 Standard-IA** | Infrequently accessed data that must be available immediately | ms | ≥ 3 | Retrieval fee; 30-day minimum |
| **S3 One Zone-IA** | **Re-creatable**, infrequently accessed data | ms | **1** | Cheaper; lost if that AZ is lost |
| **S3 Glacier Instant Retrieval** | Archive data read about once a quarter that still needs ms access | ms | ≥ 3 | 90-day minimum |
| **S3 Glacier Flexible Retrieval** | Archive data | minutes – hours | ≥ 3 | 90-day minimum |
| **S3 Glacier Deep Archive** | Long-term retention or compliance, rarely or never read | hours | ≥ 3 | Cheapest; 180-day minimum |
| **S3 Express One Zone** | Very low-latency, high-request-rate hot data (ML training scratch) | single-digit ms | 1 | Directory buckets |

- **Cost optimization for rarely used historical data:** a lifecycle rule moves it to
  Glacier (Standard → IA after 30 days → Glacier after 90 days, for example). When the
  pattern is unknown, use Intelligent-Tiering.
- Mind the minimum storage durations and per-object overhead. Do not transition millions of
  tiny objects; batch them into larger files first.

### 9.3 Block and file storage

| Service | What | Use when |
|---|---|---|
| **EBS** | A block device ("virtual disk") attached to one EC2 instance, **bound to one AZ**. It persists beyond the instance and supports snapshots, encryption, and live resizing | Databases or stateful apps on EC2. Volume types: **gp3** by default, **io2** for latency-sensitive transactional work, **st1** for large sequential throughput, **sc1** for cold data |
| **EFS** | Managed NFS shared across AZs and many clients, elastic | Several tasks or instances need the **same POSIX file system** (ECS Fargate can mount it), shared home directories, and ML iteration **without data movement** (SageMaker can train directly from EFS) |
| **FSx for Lustre** | A high-performance parallel file system, **linked to S3** | Repeated, high-throughput reads of S3 data (ML training over many runs, HPC). The first run lazy-loads from S3, and later runs reuse the cache |
| **Instance store** | Ephemeral local disk | Scratch data or caches only. It is lost when the instance stops |

For containerized backends, the rule is: **objects go to S3, shared files to EFS, and EBS is
only for self-managed stateful hosts.**
