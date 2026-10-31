# AWS infrastructure: CI/CD and deployment

> [Index](../../README.md) · **Use for:** OIDC deploy roles, ECR, migrations task, ECS rollout, health checks, autoscaling. Placeholders are defined in the index.
> **Related:** [06-ci-releases-and-docs](../../project-structure/06-ci-releases-and-docs.md)

## 14. CI/CD and deployment

**Pipeline**, extending the CI in [structure §10](../../project-structure/06-ci-releases-and-docs.md):

```
lint/test ─► build image (multi-arch or arm64) ─► push to ECR (tag = git SHA, immutable)
          ─► terraform plan (PR comment) ─► [merge] terraform apply dev
          ─► run migrations task (dev) ─► deploy ECS service (dev) ─► smoke test
          ─► promote SAME image digest ─► staging ─► (manual approval) ─► prod
```

- **CI authenticates through OIDC.** GitHub Actions and GitLab can assume a role, trusted
  with conditions on `sub` (repo, branch, environment). Each environment gets its own deploy
  role, with permissions limited to that environment's resources.
- **Build once, promote the digest.** Never rebuild for production.
- **Migrations:**
  1. `aws ecs run-task` runs the new task definition with the migration command in the
     private subnets.
  2. Wait for it, and fail the deploy on a non-zero exit code.
  3. Only then update the service.
  4. Migrations must be backward-compatible with the previous app version (expand, then
     contract).
- **ECS deployment:**
  - Rolling deployments use the **deployment circuit breaker with rollback**. Blue/green
    deployment is available when instant rollback or test traffic is needed.
  - Set `minimumHealthyPercent=100` / `maximumPercent=200` in prod.
- **Health checks** use the endpoints from the template:
  - the ALB target group checks `/health/ready`;
  - the container health check (or Lambda smoke test) checks `/health/live`;
  - give the app a health-check grace period long enough for it to start.
- **Graceful shutdown:**
  - ECS sends SIGTERM, and the app drains (as the template requires).
  - Set `stopTimeout` (up to 120 s on Fargate) and the ALB **deregistration delay** to cover
    the longest in-flight request or stream.
- **Autoscaling:**
  - The API scales by target tracking on CPU, memory, or `RequestCountPerTarget`.
  - Workers scale on SQS backlog per task.
  - Set a minimum of 2 tasks across AZs in prod.
