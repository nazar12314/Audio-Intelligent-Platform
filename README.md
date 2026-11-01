# Audio Intelligence Platform

Backend for uploading audio recordings, processing them (transcription, diarization,
information extraction), and querying them in natural language.

| Stage | Scope | Status |
|---|---|---|
| 1. Audio ingestion | Users upload recordings via S3 multipart upload; metadata is registered in PostgreSQL | **implemented** (auth is a dev stub, [ADR 0004](docs/adr/0004-auth-port-with-dev-stub.md)) |
| 2. Audio processing | Preprocessing, transcription, speaker diarization, information extraction | **VAD implemented** (validation, normalization, Silero VAD; [ADR 0005](docs/adr/0005-event-driven-processing-pipeline.md)) |
| 3. Agentic interaction | Natural-language search, summaries, audio clip generation | planned |

## Architecture

- **Ports and adapters.** Business logic in `modules/<feature>/` depends on `Protocol`
  ports. Technologies live in adapters. `core/container.py` is the single composition root.
- **Stage 1 flow.** The client uploads audio parts directly to S3 with presigned URLs; the
  API only registers, completes and verifies uploads. See
  [ADR 0001](docs/adr/0001-stage-1-ingestion-architecture.md) and the client contract in
  [API.md](API.md).
- **Processing pipeline.** Event-driven: an uploaded recording emits an event (via a
  transactional outbox) to SQS; a coordinator creates a job and queues a VAD task; VAD
  workers validate, normalize and detect speech, then report back. Workers scale
  horizontally. See [ADR 0005](docs/adr/0005-event-driven-processing-pipeline.md).
- **Infrastructure.** PostgreSQL 18 (system of record) and S3 (audio objects). Locally, S3
  is provided by RustFS ([ADR 0002](docs/adr/0002-local-s3-emulator-rustfs.md)). AWS
  resources are managed with Terraform in [`infra/`](infra/README.md)
  ([ADR 0003](docs/adr/0003-aws-foundation-stage-1.md)).
- Design conventions follow the team's internal engineering guides, kept outside this
  repository. Deviations are recorded in `docs/adr/`.

```
src/audio_platform/
├── entrypoints/              # `audio-platform-api`, `audio-platform-worker {pipeline,vad}`
├── api/                      # app factory, middleware (request ID, CORS), error envelope, health
├── core/                     # settings, container, errors, logging, readiness checks
├── infrastructure/
│   ├── db/                   # async SQLAlchemy engine, declarative base
│   └── storage/              # S3 client (aioboto3)
├── modules/
│   ├── recordings/           # Stage 1: upload lifecycle (domain, service, Postgres + S3 adapters, API)
│   └── processing/           # Stage 2: jobs, coordinator, VAD worker (PyAV, Silero ONNX)
└── shared/                   # pure helpers
```

## Prerequisites

- Python 3.14, Poetry 2.4.1
- Docker with Compose v2

## Quick start

```bash
make setup        # install deps from poetry.lock, create .env, install pre-commit hooks
```

Then either run the API on the host with hot reload:

```bash
# fill AUDIO_POSTGRES__DSN, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY in .env
# (local values are given in the comments of .env.example)
make infra-up     # Postgres + RustFS, create bucket, apply migrations
make run          # http://localhost:8000/docs
```

or run the whole stack in containers. Compose supplies the container hostnames and dev
credentials, so no secrets need to be filled in:

```bash
make up
curl localhost:8000/health/ready
```

### Against real S3 (dev environment on AWS)

After `infra/` is applied ([infra/README.md](infra/README.md)), run the API on the host with
local Postgres and the real recordings bucket:

1. Add the profile printed by `make tf-app-env` to `~/.aws/config`.
2. Put its `.env` lines into `.env`, leaving `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`
   blank.
3. Run `make aws-login`, `make infra-up`, then `make run`.

`make up` also starts the processing workers. Run more VAD workers with
`docker compose up -d --scale vad-worker=3`. Queues and their DLQs are visible in the
ElasticMQ UI at http://localhost:9325.

RustFS console: http://localhost:9001 (`rustfs-dev` / `rustfs-dev-secret`). If a default
port is taken, override `APP_HOST_PORT`, `POSTGRES_HOST_PORT`, `S3_HOST_PORT` or
`S3_CONSOLE_HOST_PORT`.

## Configuration

All settings are read by `core/config.py` from environment variables named
`AUDIO_<GROUP>__<FIELD>`. Every setting is documented in [`.env.example`](.env.example).

| Group | Purpose | Required |
|---|---|---|
| `AUDIO_POSTGRES__*` | DSN (secret, `postgresql+asyncpg://…`), pool sizing, timeouts | `DSN` |
| `AUDIO_STORAGE__*` | Recordings bucket | `BUCKET` |
| `AUDIO_AWS__*` | Region, local endpoint override, S3 client timeouts and retries | — |
| `AUDIO_API__*` | Bind address, CORS origins, docs toggle | — |

AWS credentials are never app settings. The SDK's default credential chain reads them:
`AWS_*` env vars locally, the task role on AWS. The app refuses to start, with exit code 2
and one line per field, when a required setting is missing or invalid.

## Make targets

| Target | Description |
|---|---|
| `setup` | First-time setup: `install` + `env` + `hooks` |
| `install` | Install deps from `poetry.lock` |
| `env` | Create `.env` from `.env.example` (never overwrites) |
| `run` | API on the host with hot reload |
| `lint` / `format` | Ruff check / auto-fix |
| `typecheck` | mypy (strict) |
| `test` | Unit + API tests (no Docker) |
| `test-integration` | Integration tests against real Postgres and RustFS (Docker) |
| `cov` | Whole suite with coverage (gate: 80%) |
| `migrate` | `alembic upgrade head` against the DB in `.env` |
| `migration m="…"` | Autogenerate `migrations/versions/<timestamp>_<rev>_<slug>.py` |
| `migrations-check` | Fail unless migrations have exactly one head (run in CI) |
| `worker-pipeline` / `worker-vad` | Run the pipeline coordinator / a VAD worker on the host |
| `db-shell` / `db-stats` | `psql` on the local database / overview of migrations, recordings, tables, connections |
| `infra-up` / `up` / `down` / `logs` | Docker Compose lifecycle |
| `aws-login` | SSO login to AWS (profile `audio-platform-dev`) |
| `tf-bootstrap` / `tf-init` / `tf-plan` / `tf-apply` | Terraform for the dev environment ([infra/README.md](infra/README.md)) |
| `tf-app-env` | Print app `.env` lines and AWS profile from Terraform outputs |
| `tf-fmt` / `tf-lint` | Format / fmt check, validate, tflint, checkov |

## Testing

| Layer | Type | Location |
|---|---|---|
| Domain, core logic | unit, no I/O | `tests/unit/` |
| HTTP API | ASGI client with a container built from fakes | `tests/api/` |
| Adapters, infrastructure | testcontainers: Postgres 18, RustFS | `tests/integration/` (`@pytest.mark.integration`) |

In-memory fakes of ports live in `tests/fakes/`. Contract suites in `tests/contracts/` run
against both the fakes and the real adapters, so the two cannot drift apart. Tests never
read `.env`; they build `Settings` explicitly (`tests/conftest.py::make_settings`).

## Releases

Commits follow [Conventional Commits](https://www.conventionalcommits.org/) with the feature
as scope, for example `feat(recordings): presign upload parts`. On `main`, CI runs
python-semantic-release, which bumps the version, tags `vX.Y.Z`, and updates `CHANGELOG.md`.
