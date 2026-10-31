# Project structure: Dependencies and lock files

> [Index](../README.md) · **Use for:** writing pyproject.toml, adding/upgrading packages, lock-file rules. Placeholders are defined in the index.

## 3. Dependencies and lock files

### `pyproject.toml`: project and dependency groups (Poetry 2.x, PEP 621)

```toml
[project]
name = "<service>"
version = "0.1.0"
description = "<one line>"
requires-python = ">=3.13,<3.15"
readme = "README.md"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "httpx>=0.28",
    # infrastructure drivers: add ONLY those the project uses
    # "sqlalchemy[asyncio]>=2.0", "asyncpg>=0.30", "alembic>=1.14",   # PostgreSQL
    # "pymongo>=4.10",                                                 # MongoDB (async API)
    # "redis>=5.2",                                                    # Redis
    # "aio-pika>=9.5",                                                 # RabbitMQ
    # "aiokafka>=0.12",                                                # Kafka
]

[project.scripts]
<service>-api = "<package>.entrypoints.api:main"
<service>-worker = "<package>.entrypoints.worker:main"     # conditional

[tool.poetry]
packages = [{ include = "<package>", from = "src" }]

[tool.poetry.group.dev.dependencies]
ruff = "^0.8"
mypy = "^1.13"
pytest = "^8.3"
pytest-asyncio = "^0.24"
pytest-cov = "^6.0"
pre-commit = "^4.0"
python-semantic-release = "^9.15"
# testcontainers = { version = "^4.8", extras = ["postgres", "mongodb", "redis", "rabbitmq", "kafka"] }

[build-system]
requires = ["poetry-core>=2.0"]
build-backend = "poetry.core.masonry.api"
```

The version numbers in the snippets in this document are examples. When setting up a
project, take the current stable releases and pin them.

### Rules

- **Commit the lock file**, every time. Never edit it by hand. Regenerate it only with
  `poetry lock` / `uv lock`.
- Every change to the dependencies goes in a single commit that contains both
  `pyproject.toml` and the updated lock file.
- CI checks that the lock file is consistent (`poetry check --lock` / `uv lock --check`) and
  installs from it (`poetry sync` / `uv sync --frozen`).
- A package the code imports at runtime belongs in the main dependencies. Do not rely on a
  dev tool pulling it in transitively.
- Bound major versions where an upgrade breaks things. When you add an upper ceiling
  (`<2.0`) or an exact pin, add a comment with the reason, the advisory, or the issue link.
- Keep tooling-only dependencies in groups (`dev`, `docs`, or an optional `tools` group).
  Production images install `--only main`.
- Virtualenv location: with Poetry, `poetry.toml` contains
  `[virtualenvs] in-project = true`; uv creates `.venv/` by default. `.venv/` is listed in
  `.gitignore`.
