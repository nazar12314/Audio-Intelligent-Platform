# 0003. AWS foundation for Stage 1

- **Status:** accepted
- **Date:** 2026-10-31

## Context

Stage 1 needs real S3 for the upload flow: presigned multipart uploads, CORS, lifecycle
rules. The app is not deployed yet; it runs on developer machines.

## Decision

- **Region:** `eu-central-1` (Frankfurt). Keeps recordings in the EU.
- **Accounts:** a single AWS account, the existing one, which is also the organization's
  management account (IAM Identity Center requires an organization). The dev environment
  lives there, named `audio-platform-dev-*`. This **deviates from the guides**, which keep
  workloads out of the management account and give each environment its own account. It
  was chosen for simplicity while there is one developer and no production data.
- **Access:** people sign in through IAM Identity Center (SSO) to that account, with no IAM
  users or access keys. The app uses the role `audio-platform-dev-app` (S3 on `users/*` of the recordings
  bucket only), assumed from SSO locally; it becomes the ECS task role later.
- **IaC:** Terraform, in `infra/` inside this repo. State lives in a per-account S3 bucket
  with native locking. The bootstrap root keeps local state.
- **Apply flow:** local `plan` / `apply` for now. CI runs fmt, validate, tflint and checkov.
  Plan on PR and apply on merge through GitHub OIDC arrive with the app deployment.
- **Data stores:** S3 on AWS now. **PostgreSQL stays local (docker compose)** until the app
  runs on AWS. A private RDS instance is unreachable from laptops without a tunnel host,
  and costs about $20–25/month before it serves anything.
- **Cost guardrails:** a monthly budget with alerts at 50/80/100% actual and 100% forecast.

## Consequences

- The management account is exempt from service control policies, and its admins can
  change the organization and billing. A leaked dev credential therefore has a larger
  blast radius than in a member account. Mitigations: MFA on root and on the SSO user,
  short SSO sessions, the least-privilege app role for the app itself, `allowed_account_ids`
  in every Terraform root, and the budget alert.
- **Revisit before production:** put `prod` (and ideally `dev`) in member accounts. The
  modules need no changes; only the `envs/*` tfvars, the backend bucket, and the SSO
  profile change.

- While the app runs locally against real S3, the local Postgres and the S3 bucket are
  separate sources of truth: wiping one leaves dangling references in the other. This is
  acceptable for dev data.
- The next infrastructure step (deploying the app) adds, together: VPC (`network`
  module), RDS PostgreSQL in private-data subnets, ECR, ECS Fargate with ALB, Secrets
  Manager, a GitHub OIDC deploy role, and the S3 → SQS trigger for Stage 2.
- Not yet enabled: Cost Anomaly Detection, CloudTrail / GuardDuty / Config, and SCPs. Add
  them to the organization baseline before production.
