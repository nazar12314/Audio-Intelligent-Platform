# AWS infrastructure: Infrastructure as code

> [Index](../../README.md) · **Use for:** Terraform/CDK layout, remote state, modules, plan/apply rules. Placeholders are defined in the index.

## 4. Infrastructure as code

**Default: Terraform (or OpenTofu).** Use **AWS CDK (Python)** instead when the team wants
the infrastructure in the same language as the app. Pick one per organization, not per
project.

### 4.1 Layout (inside the service repo, or in a dedicated `<project>-infra` repo)

```
infra/
├── bootstrap/                 # once per account: state bucket, OIDC provider, deploy roles
├── modules/                   # reusable, versioned, no environment-specific values
│   ├── network/               # VPC, subnets, NAT, endpoints, flow logs
│   ├── ecs-cluster/
│   ├── ecs-service/           # task def + service + autoscaling + alarms + log group
│   ├── alb/
│   ├── rds-postgres/          # or aurora-postgres/
│   ├── elasticache/
│   ├── sqs-queue/             # queue + DLQ + alarms
│   ├── s3-bucket/             # encryption, versioning, lifecycle, BPA, TLS-only policy
│   ├── secrets/
│   └── <component>/
├── envs/
│   ├── dev/        { main.tf, variables.tf, terraform.tfvars, backend.tf }
│   ├── staging/
│   └── prod/
└── README.md                  # how to plan/apply, who owns what, runbooks links
```

### 4.2 Rules

- **Remote state:** an S3 bucket per account, with versioning and encryption turned on.
  Use S3-native state locking (`use_lockfile = true` in Terraform ≥ 1.10). Older setups use a
  DynamoDB lock table.
- **One state per environment**, split further by blast radius (`network`, `data`, `app`)
  once the stack grows large.
- **Pin the versions** of Terraform, the AWS provider, and every module. Commit
  `.terraform.lock.hcl`, which is the IaC equivalent of the Python lock file.
- `envs/*` contain **only** module calls and variables. Resources are defined only in
  modules.
- **Plan on every PR** and post the plan as a comment. **Apply only from CI**, on merge, with
  a manual approval for production.
- **Linting:** `terraform fmt -check`, `terraform validate`, `tflint`, and a security
  scanner (`checkov` / `trivy config`) run in CI and in pre-commit
  (`antonbabenko/pre-commit-terraform`).
- **Data stores get `prevent_destroy` / deletion protection.** Never store a secret value in
  Terraform state: create the secret container in Terraform and set the value out of band,
  or let RDS manage the master password.
- Outputs that the app needs (queue URLs, bucket names, endpoints) become **env vars on the
  task definition**. They are never hard-coded in the app.
