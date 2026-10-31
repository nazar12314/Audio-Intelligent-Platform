# Agent Guides: Index

A knowledge base for setting up and evolving backend projects. It covers:

- the repository scaffold;
- the application architecture;
- AWS infrastructure.

It is project-agnostic: use the parts the project needs.

## How to use this index (read this first)

1. **Do not read every file.** Find the task in the [routing table](#routing-by-task), then
   open only the files listed for it. Files are short (about 20–150 lines) and self-contained.
2. Follow a file's **Related:** links only when the task touches that topic too.
3. **Cross-references** look like `[architecture §8.2](...)`. The label names the guide
   (`structure`, `architecture`, `aws`), and the number is the section heading inside the
   target file.
4. **Precedence:** the existing project's deliberate conventions override these guides.
   Record every deviation in the project's README or in an ADR.
5. AWS is **optional**. Open `aws-infrastructure/` only when the project is deployed to AWS.
   Check AWS numbers, quotas and service names against the current AWS docs (see the note
   at the top of [aws-infrastructure/foundation/01](aws-infrastructure/foundation/01-principles-and-compute.md)).

## Placeholders

| Placeholder | Meaning | Example |
|---|---|---|
| `<service>` | Repository / service name, kebab-case | `chatbot-backend` |
| `<package>` | Python package name, snake_case | `chatbot_backend` |
| `<APP>` | Env-var prefix, upper-case | `CHATBOT` |
| `<feature>` | Feature module / bounded context | `auth`, `chat` |
| `<project>` | Short project name for cloud resources, kebab-case | `chatbot` |
| `<env>` | Deployment environment | `dev`, `staging`, `prod` |
| `<region>` | Primary AWS region | `eu-central-1` |

## Rules that always apply

These hold without opening any other file:

- Business logic depends on **ports** (Protocols). Technologies live in **adapters**. One
  **composition root** chooses the implementations.
- Env vars are read **only** through the `Settings` class. **Secrets have no defaults** and
  are blank in `.env.example`.
- Lock files and the IaC lock are **committed**, and dependencies are installed from them.
  Tool and image versions are **pinned**.
- Every external call has a **timeout and a retry policy**. Every consumer is
  **idempotent**. Every queue has a **DLQ**.
- The app runs locally with `docker compose`. The cloud only changes adapters and
  configuration, never business logic.
- CI runs the **whole** suite and only checks. It never auto-fixes.

## Folder map

```
agent-guides/
├── README.md                          ← this index
├── project-structure/                 repo scaffold & tooling (no business design)
│   ├── 01-toolchain-and-layout.md
│   ├── 02-dependencies-and-lockfiles.md
│   ├── 03-code-quality-and-tests.md
│   ├── 04-env-files-and-makefile.md
│   ├── 05-docker-and-local-infra.md
│   ├── 06-ci-releases-and-docs.md
│   └── 07-setup-checklist.md
├── backend-architecture/              how code inside src/<package>/ is designed
│   ├── 01-principles-and-layers.md
│   ├── 02-core-config-di-errors-lifecycle.md
│   ├── 03-choosing-infrastructure.md
│   ├── 04-database-management.md
│   ├── 05-caching-and-sessions.md
│   ├── 06-messaging-and-background-jobs.md
│   ├── 07-external-apis-llm-rag.md
│   ├── 08-auth.md
│   ├── 09-api-design.md
│   ├── 10-observability.md
│   ├── 11-testing.md
│   ├── 12-security.md
│   └── 13-anti-patterns.md
└── aws-infrastructure/                only when the project runs on AWS
    ├── foundation/                    decide first: compute, accounts, IaC, service mapping
    │   ├── 01-principles-and-compute.md
    │   ├── 02-accounts-and-environments.md
    │   ├── 03-infrastructure-as-code.md
    │   └── 04-service-mapping.md
    ├── services/                      per-category AWS services and when to use each
    │   ├── networking.md
    │   ├── messaging-streaming.md
    │   ├── data-stores.md
    │   ├── storage.md
    │   ├── ai-ml.md
    │   └── data-engineering.md
    ├── operations/                    running it: secrets, security, deploy, DR, cost, local testing
    │   ├── secrets-and-config.md
    │   ├── security-and-observability.md
    │   ├── cicd-deployment.md
    │   ├── reliability-and-dr.md
    │   ├── local-dev-and-testing.md
    │   └── cost.md
    ├── reference-architectures.md
    └── checklist-and-anti-patterns.md
```

## Routing by task

Read the files in the order listed. Prefixes: **PS** = `project-structure/`,
**BA** = `backend-architecture/`, **AWS** = `aws-infrastructure/`.

| Task | Read |
|---|---|
| **Bootstrap a new backend repo** | PS/07 (checklist) → PS/01 → PS/02 → PS/03 → PS/04 → PS/05 → BA/01 → BA/02. Then the BA files for each component the project needs (rows below) |
| Decide which databases, caches or brokers a project needs | BA/03 → the matching rows below |
| Add a feature module | BA/01 (module anatomy) → BA/02 (wiring in the container) → BA/11 |
| Configuration, DI container, errors, startup and shutdown | BA/02 |
| Add or change a **database** (Postgres, Mongo, migrations) | BA/04 → PS/05 (compose service) → BA/11 |
| Add **caching** or **sessions** (Redis) | BA/05 → PS/05 |
| Add **messaging** (RabbitMQ, Kafka), workers, scheduled or long jobs | BA/06 → PS/05 |
| Call third-party APIs; add **LLM / embeddings / RAG** | BA/07 → BA/05 (LLM caching) → BA/06 (ingestion jobs) |
| Add **authentication / authorization**, rate limiting | BA/08 → BA/05 (session store) |
| Design or change HTTP / WS / SSE endpoints | BA/09 |
| Logging, metrics, tracing, health checks | BA/10 |
| Write or organize tests | BA/11 → PS/03 |
| Security review of the app | BA/12 → BA/13 |
| Code or design review | BA/13 → the BA file for the area touched |
| Dependencies, lock files, upgrades | PS/02 |
| Lint, type-check, pre-commit | PS/03 |
| Dockerfile, compose, local infrastructure | PS/05 |
| CI pipeline, releases, repo docs | PS/06 |
| **Put a project on AWS** | AWS/checklist-and-anti-patterns (§19) → AWS/foundation/01 → 02 → 03 → 04. Then the services and operations files the checklist points to |
| Pick the AWS service for a given port | AWS/foundation/04 → the matching AWS/services file |
| VPC, subnets, endpoints, DNS, TLS, WAF, ALB vs API Gateway | AWS/services/networking |
| SQS / SNS / EventBridge / Kinesis / MSK / Amazon MQ | AWS/services/messaging-streaming → BA/06 |
| RDS / Aurora / DocumentDB / DynamoDB / ElastiCache / vector search | AWS/services/data-stores → BA/04 |
| S3, storage classes, lifecycle, EBS / EFS / FSx | AWS/services/storage |
| Bedrock, SageMaker | AWS/services/ai-ml → BA/07 |
| Data lake, ETL, analytics (Glue, Athena, Redshift, DMS, EMR) | AWS/services/data-engineering → AWS/services/storage |
| Secrets and config on AWS | AWS/operations/secrets-and-config → BA/02 |
| Deploy pipeline, ECS rollout, migrations on AWS | AWS/operations/cicd-deployment → PS/06 |
| IAM, security services, CloudWatch, alarms | AWS/operations/security-and-observability |
| Backups, Multi-AZ, DR, quotas | AWS/operations/reliability-and-dr |
| Cost optimization | AWS/operations/cost |
| Test AWS adapters locally (moto, LocalStack) | AWS/operations/local-dev-and-testing → BA/11 |
| Need a starting diagram (API + workers, LLM chatbot, data/ML pipeline) | AWS/reference-architectures |

## Catalog

### project-structure/: repository scaffold and tooling

| File | Covers |
|---|---|
| [01-toolchain-and-layout](project-structure/01-toolchain-and-layout.md) | Default toolchain; full repository skeleton, including the `src/<package>/` layers; naming rules |
| [02-dependencies-and-lockfiles](project-structure/02-dependencies-and-lockfiles.md) | `pyproject.toml` (Poetry 2 / uv), dependency groups, lock-file rules |
| [03-code-quality-and-tests](project-structure/03-code-quality-and-tests.md) | Ruff, mypy, pre-commit, pytest/coverage configuration |
| [04-env-files-and-makefile](project-structure/04-env-files-and-makefile.md) | `.env.example` rules, `.gitignore`, `.editorconfig`, Makefile targets |
| [05-docker-and-local-infra](project-structure/05-docker-and-local-infra.md) | Multi-stage Dockerfile, allow-list `.dockerignore`, compose catalog (Postgres, Mongo, Redis, RabbitMQ, Kafka, Qdrant) |
| [06-ci-releases-and-docs](project-structure/06-ci-releases-and-docs.md) | CI stages, semantic-release, README / API.md / ADRs |
| [07-setup-checklist](project-structure/07-setup-checklist.md) | Ordered bootstrap steps and verification |

### backend-architecture/: application design

| File | Covers |
|---|---|
| [01-principles-and-layers](backend-architecture/01-principles-and-layers.md) | Ports and adapters, layer import rules (with lint enforcement), feature module anatomy |
| [02-core-config-di-errors-lifecycle](backend-architecture/02-core-config-di-errors-lifecycle.md) | Settings, composition root, null objects, error hierarchy, app factory and lifespan |
| [03-choosing-infrastructure](backend-architecture/03-choosing-infrastructure.md) | Decision table for SQL, document, Redis, vector, queue, broker, stream, blob, search; steps to add any component |
| [04-database-management](backend-architecture/04-database-management.md) | Repository and unit of work, PostgreSQL + Alembic, MongoDB (indexes, schema versions, migrations), Redis as storage |
| [05-caching-and-sessions](backend-architecture/05-caching-and-sessions.md) | Cache port, cache-aside, keys, TTLs, stampede protection, LLM cache keys, auth vs conversation sessions |
| [06-messaging-and-background-jobs](backend-architecture/06-messaging-and-background-jobs.md) | Event envelope, at-least-once delivery, outbox, retries and DLQ, RabbitMQ, Kafka, background, scheduled and long jobs |
| [07-external-apis-llm-rag](backend-architecture/07-external-apis-llm-rag.md) | Outbound HTTP rules, LLM and embedding ports, streaming, RAG ingestion and retrieval |
| [08-auth](backend-architecture/08-auth.md) | Local vs OIDC vs service auth, JWT and refresh tokens, RBAC and ownership, abuse protection |
| [09-api-design](backend-architecture/09-api-design.md) | Versioning, schemas, error format, idempotency keys, 202 + jobs, OpenAPI, CORS |
| [10-observability](backend-architecture/10-observability.md) | Structured logs, request ID propagation, event codes, redaction, metrics, tracing, health |
| [11-testing](backend-architecture/11-testing.md) | Test type per layer, fakes, port contract tests, determinism |
| [12-security](backend-architecture/12-security.md) | Secrets, injection, uploads, audit log, LLM-specific guards |
| [13-anti-patterns](backend-architecture/13-anti-patterns.md) | What to avoid, and what to do instead |

### aws-infrastructure/: AWS (optional)

| File | Covers |
|---|---|
| [foundation/01-principles-and-compute](aws-infrastructure/foundation/01-principles-and-compute.md) | Cloud-agnostic-app principles; compute decision table (ECS, Lambda, EKS, Batch, Glue, SageMaker) |
| [foundation/02-accounts-and-environments](aws-infrastructure/foundation/02-accounts-and-environments.md) | Organizations, an account per environment, SSO, OIDC, SCPs, naming, tags |
| [foundation/03-infrastructure-as-code](aws-infrastructure/foundation/03-infrastructure-as-code.md) | Terraform/CDK layout, remote state, modules and environments, plan/apply rules |
| [foundation/04-service-mapping](aws-infrastructure/foundation/04-service-mapping.md) | Each architecture port mapped to its AWS default and alternatives |
| [services/networking](aws-infrastructure/services/networking.md) | VPC tiers, NAT, endpoints, security groups, edge (Route 53, ACM, WAF, CloudFront), ALB vs API Gateway |
| [services/messaging-streaming](aws-infrastructure/services/messaging-streaming.md) | SQS, SNS, EventBridge, Kinesis vs SQS vs MSK, Firehose, Flink, Amazon MQ |
| [services/data-stores](aws-infrastructure/services/data-stores.md) | RDS/Aurora, Atlas/DocumentDB, DynamoDB, ElastiCache, vector search options |
| [services/storage](aws-infrastructure/services/storage.md) | S3 baseline, storage classes, lifecycle, EBS/EFS/FSx |
| [services/ai-ml](aws-infrastructure/services/ai-ml.md) | Bedrock, SageMaker endpoint types, training, MLOps, EDA tools |
| [services/data-engineering](aws-infrastructure/services/data-engineering.md) | Lake layout, data formats, Glue, Athena, Redshift (Spectrum), DMS, EMR, streaming ingestion |
| [operations/secrets-and-config](aws-infrastructure/operations/secrets-and-config.md) | Secrets Manager, SSM, env-var injection, IAM roles, KMS |
| [operations/security-and-observability](aws-infrastructure/operations/security-and-observability.md) | Org security services, IAM practice, CloudWatch, X-Ray, alarms, dashboards |
| [operations/cicd-deployment](aws-infrastructure/operations/cicd-deployment.md) | OIDC, build once and promote, migration task, ECS rollout, health checks, shutdown, autoscaling |
| [operations/reliability-and-dr](aws-infrastructure/operations/reliability-and-dr.md) | RTO/RPO tiers, Multi-AZ, AWS Backup, restore drills, quotas |
| [operations/local-dev-and-testing](aws-infrastructure/operations/local-dev-and-testing.md) | AWS settings in the app, SDK usage, moto, LocalStack |
| [operations/cost](aws-infrastructure/operations/cost.md) | Visibility, compute, network, storage, database, and LLM cost levers |
| [reference-architectures](aws-infrastructure/reference-architectures.md) | Container API + workers, LLM chatbot, data/ML pipeline |
| [checklist-and-anti-patterns](aws-infrastructure/checklist-and-anti-patterns.md) | Ordered steps for adding AWS to a project; AWS anti-patterns |

## Maintaining these guides

- **One topic per file.** Keep a file under about 150 lines. When it grows past that, split
  it and add the new file to the folder map, the routing table, and the catalog.
- **Every file starts with this header:**
  - `# <Guide>: <Topic>`;
  - a line with `[Index](…) · **Use for:** …`;
  - an optional `**Related:**` line.
- Section numbers (`## 6. …`) are stable IDs used by cross-references. When adding sections,
  append a new number rather than renumbering existing ones.
- Keep the guides project-agnostic. Put project specifics in the project's own README or ADRs.
