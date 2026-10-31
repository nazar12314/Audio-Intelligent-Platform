# AWS infrastructure: Accounts and environments

> [Index](../../README.md) · **Use for:** AWS Organizations, accounts per env, SSO, OIDC, SCPs, naming, tags. Placeholders are defined in the index.

## 3. Account and environment foundation

- **AWS Organizations, with one account per environment:** `<project>-dev`,
  `<project>-staging`, `<project>-prod`. Small projects may share a non-production account,
  but **production is always separate**. Optional shared accounts are `security` / `log-archive`
  (CloudTrail, Config) and `shared-services` (ECR, DNS).
- **Human access** goes through **IAM Identity Center** (SSO) with permission sets. There are
  no IAM users and no access keys for people. Turn on MFA everywhere, and lock the root
  account away.
- **Machine access:**
  - CI uses **OIDC federation** to assume a deploy role ([aws §14](../operations/cicd-deployment.md)). There are no stored keys.
  - Workloads use **IAM roles**: ECS task roles, Lambda execution roles, and EC2 instance
    profiles.
- **Guardrails** are service control policies (SCPs) that:
  - deny leaving the organization;
  - deny disabling CloudTrail, GuardDuty, or Config;
  - restrict regions to the approved list;
  - deny creating IAM users or access keys.
- **Region:** pick one primary region close to the users and compliant with data-residency
  rules. Plan for a second region only if the RTO/RPO requires it ([aws §15](../operations/reliability-and-dr.md)).
- **Naming:** `<project>-<env>-<component>`, for example `chatbot-prod-api` or
  `chatbot-prod-ingest-queue`.
- **Mandatory tags on every resource:** `Project`, `Environment`, `Owner`, `CostCenter`,
  `ManagedBy=terraform`. Apply them as provider default tags.
