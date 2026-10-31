# Project structure: Docker and local infrastructure

> [Index](../README.md) · **Use for:** writing the Dockerfile, .dockerignore, docker-compose.yml (Postgres/Mongo/Redis/RabbitMQ/Kafka/Qdrant). Placeholders are defined in the index.
> **Related:** [03-choosing-infrastructure](../backend-architecture/03-choosing-infrastructure.md)

## 8. Docker

### `docker/app/Dockerfile` (multi-stage, non-root)

```dockerfile
ARG PYTHON_IMAGE=python:3.13-slim          # pin a patch version in real projects
FROM ${PYTHON_IMAGE} AS builder
ENV PIP_NO_CACHE_DIR=1 POETRY_VIRTUALENVS_IN_PROJECT=true POETRY_NO_INTERACTION=1
WORKDIR /app
RUN pip install "poetry==<pinned>"
COPY pyproject.toml poetry.lock README.md ./
RUN poetry install --only main --no-root   # dependency layer: cached until the lock changes
COPY src ./src
RUN poetry install --only main             # installs the project itself into .venv

FROM ${PYTHON_IMAGE} AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PATH="/app/.venv/bin:$PATH"
WORKDIR /app
# System packages only if needed, each with a comment saying why:
# RUN apt-get update && apt-get install -y --no-install-recommends <pkg> && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 10001 app
COPY --from=builder --chown=app /app/.venv ./.venv
COPY --from=builder --chown=app /app/src ./src
# COPY --chown=app migrations ./migrations          # conditional
USER app
EXPOSE 8000
CMD ["<service>-api"]
```

- The same image runs every process type. Compose or the orchestrator picks the process with
  `command:` (`<service>-api`, `<service>-worker`, the migration command).
- Use build `ARG`s or extra stages for image flavours, for example a `dev` stage with the dev
  dependencies. Each extra flavour gets a CI job that builds it and starts it.
- Never `COPY . .`. Copy only what the image needs.

### `.dockerignore` (allow-list)

```
*
!pyproject.toml
!poetry.lock
!README.md
!src/
!migrations/
**/__pycache__/
**/*.py[cod]
```

---

## 9. Local infrastructure (`docker-compose.yml`)

Compose holds the app and **only** the infrastructure the project uses. The service catalog
below lists the usual candidates. Keep the ones you need.

```yaml
x-app: &app
  build: { context: ., dockerfile: docker/app/Dockerfile }
  env_file: .env
  restart: unless-stopped
  networks: [backend]

services:
  app:
    <<: *app
    command: ["<service>-api"]
    ports: ["8000:8000"]
    depends_on:
      # list only what the app needs; `service_healthy` waits for the healthcheck
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }
      migrate: { condition: service_completed_successfully }

  worker:                              # conditional: background consumers / jobs
    <<: *app
    command: ["<service>-worker"]

  migrate:                             # conditional: one-shot schema/index migration
    <<: *app
    command: ["<migration command>"]
    restart: "no"

  # ── Infrastructure catalog: keep only what the project uses; pin tags ─────────
  postgres:
    image: postgres:17-alpine
    environment: { POSTGRES_USER: app, POSTGRES_PASSWORD: app, POSTGRES_DB: app }
    volumes: [postgres_data:/var/lib/postgresql/data]
    healthcheck: { test: ["CMD-SHELL", "pg_isready -U app"], interval: 5s, retries: 10 }
    networks: [backend]

  mongo:
    image: mongo:8
    volumes: [mongo_data:/data/db]
    healthcheck: { test: ["CMD", "mongosh", "--quiet", "--eval", "db.adminCommand('ping')"], interval: 10s, retries: 10 }
    networks: [backend]

  redis:
    image: redis:7-alpine
    command: ["redis-server", "--appendonly", "yes"]
    volumes: [redis_data:/data]
    healthcheck: { test: ["CMD", "redis-cli", "ping"], interval: 5s, retries: 10 }
    networks: [backend]

  rabbitmq:
    image: rabbitmq:4-management-alpine
    ports: ["15672:15672"]            # management UI, dev only
    volumes: [rabbitmq_data:/var/lib/rabbitmq]
    healthcheck: { test: ["CMD", "rabbitmq-diagnostics", "-q", "check_port_connectivity"], interval: 15s, retries: 10 }
    networks: [backend]

  kafka:                               # single-node KRaft, dev only
    image: apache/kafka:3.9.0
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_LISTENERS: PLAINTEXT://:9092,CONTROLLER://:9093
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092
      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT
      KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka:9093
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
    volumes: [kafka_data:/var/lib/kafka/data]
    healthcheck: { test: ["CMD-SHELL", "/opt/kafka/bin/kafka-broker-api-versions.sh --bootstrap-server localhost:9092"], interval: 15s, retries: 10 }
    networks: [backend]

  qdrant:                              # vector store (alternative: pgvector in postgres)
    image: qdrant/qdrant:v1.12.5
    volumes: [qdrant_data:/qdrant/storage]
    networks: [backend]

volumes: { postgres_data: {}, mongo_data: {}, redis_data: {}, rabbitmq_data: {}, kafka_data: {}, qdrant_data: {} }
networks: { backend: {} }
```

Rules:

- Pin every image tag. Never use `:latest`.
- Every stateful service gets a named volume, and every dependency gets a healthcheck.
  Healthchecks stay cheap: no heavy CLI started every few seconds.
- Use `depends_on` with `condition: service_healthy` or
  `condition: service_completed_successfully`. Never use a bare `depends_on`.
- Publish infrastructure ports to the host only when the app runs on the host
  (`make run` + `make infra-up`).
- Compose profiles (`profiles: [rag]`) can group optional components.
- Credentials in compose are for development only. They never appear in a production example.
