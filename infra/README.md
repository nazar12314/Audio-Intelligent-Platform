# Infrastructure (Terraform)

AWS resources for the platform, managed only through Terraform. Nothing is created by hand
in the console. Decisions are recorded in [ADR 0003](../docs/adr/0003-aws-foundation-stage-1.md).

```
infra/
├── bootstrap/        # once per account: Terraform state bucket, S3 account BPA, monthly budget (local state)
├── modules/          # reusable; resources live only here
│   ├── s3-bucket/        # BPA, ownership enforced, SSE, TLS-only, versioning, lifecycle, CORS
│   ├── account-baseline/ # account-level S3 public access block + budget alerts
│   └── app-role/         # least-privilege role for the app (local dev now, ECS task role later)
└── envs/
    └── dev/          # module calls only; remote state in the bootstrap bucket
```

| Environment | AWS account | Contains (Stage 1) |
|---|---|---|
| `dev` | the existing (management) account; no separate member accounts | recordings bucket, app role, budget |

Resource names are prefixed `audio-platform-dev-*`, so a later environment can live in the
same account or move to its own account without renaming.

PostgreSQL stays in docker compose until the app runs on AWS. RDS, VPC and ECS come in that
step.

## Prerequisites

- Terraform `>= 1.14, < 2.0` (CI pins 1.14.6), AWS CLI v2, Docker (for `make tf-lint`).
- An IAM Identity Center login to the account, configured as profile `audio-platform-dev`.
  Override it with
  `make … AWS_PROFILE_DEV=<name>`.
- The repo is public, so account IDs and emails live only in git-ignored files:
  `terraform.tfvars` (copy from `terraform.tfvars.example`) and `envs/dev/backend.hcl`
  (generated).

## First-time setup

```bash
make aws-login                     # browser SSO login
cp infra/bootstrap/terraform.tfvars.example infra/bootstrap/terraform.tfvars   # fill in
make tf-bootstrap                  # state bucket + baseline; writes infra/envs/dev/backend.hcl
cp infra/envs/dev/terraform.tfvars.example infra/envs/dev/terraform.tfvars     # fill in
make tf-init
make tf-plan                       # review the plan
make tf-apply                      # applies exactly the reviewed plan
make tf-app-env                    # .env lines + ~/.aws/config profile for the app
```

`bootstrap/terraform.tfstate` is local and git-ignored. Keep it: it tracks the state
bucket. If it is lost, re-import the resources (`terraform import`); nothing is recreated.

## Day to day

| Target | What it does |
|---|---|
| `make aws-login` | Refresh the SSO session (8 h) |
| `make tf-plan` / `make tf-apply` | Plan into `tfplan`, then apply exactly that plan |
| `make tf-fmt` | Format |
| `make tf-lint` | fmt check, validate, tflint (AWS ruleset), checkov. Needs no AWS access; CI runs the same |

## Rules

- Resources are defined only in `modules/`. `envs/*` contain module calls and variables.
- Every provider sets `allowed_account_ids`, so Terraform refuses to touch any account
  except the one in `terraform.tfvars`, whatever `AWS_PROFILE` is active.
- Default tags on everything: `Project`, `Environment`, `Owner`, `CostCenter`,
  `ManagedBy=terraform`.
- Data stores have `prevent_destroy`. Deleting one is a deliberate code change.
- Version pins: Terraform `required_version`, AWS provider `~> 6.71`. The
  `.terraform.lock.hcl` files are committed, with hashes for macOS and Linux.
- Apply runs locally for now. Plan and apply through GitHub Actions with OIDC comes with the
  app deployment.
