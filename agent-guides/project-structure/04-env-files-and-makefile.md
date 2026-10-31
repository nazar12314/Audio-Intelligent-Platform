# Project structure: Environment files and Makefile

> [Index](../README.md) · **Use for:** writing .env.example, .gitignore, .editorconfig, Makefile targets. Placeholders are defined in the index.
> **Related:** [02-core-config-di-errors-lifecycle](../backend-architecture/02-core-config-di-errors-lifecycle.md)

## 6. Environment files

- **`.env.example`** is committed. It lists **every** setting with a comment that gives its
  meaning, units, allowed values, and default. Secrets are left blank: `<APP>_JWT_SECRET=`.
- **`.env`** is git-ignored and created from the example by `make env`. That target never
  overwrites an existing `.env`.
- The env-var naming scheme is `<APP>_<GROUP>__<FIELD>`, for example `CHATBOT_REDIS__URL`.
  The `__` separator marks a nested group.
- Compose loads `.env` through `env_file:`. Neither the image nor the repository ever
  contains a real secret.

### `.gitignore` (minimum)

```
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
dist/
build/
.env
.env.*
!.env.example
logs/
data/
.DS_Store
.idea/
.vscode/
```

### `.editorconfig`

```ini
root = true
[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
indent_style = space
indent_size = 4
trim_trailing_whitespace = true
[*.{yml,yaml,json,toml,md}]
indent_size = 2
```

---

## 7. Makefile

Every target prints what it is doing. `make help` is the default target.

```makefile
.DEFAULT_GOAL := help
.PHONY: help setup install env hooks run worker lint format typecheck test test-integration \
        cov migrate up down logs infra-up clean

help:            ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-18s %s\n",$$1,$$2}'

setup: install env hooks   ## First-time local setup
install:         ## Install deps from the lock file
	poetry sync
env:             ## Create .env from .env.example (never overwrites)
	@test -f .env || (cp .env.example .env && echo ".env created — fill in secrets")
hooks:           ## Install pre-commit hooks
	poetry run pre-commit install

run:             ## Run the API locally (hot reload)
	poetry run uvicorn <package>.entrypoints.api:create_app --factory --reload
worker:          ## Run the background worker locally (conditional)
	poetry run python -m <package>.entrypoints.worker

lint:            ## Check lint + format (no changes)
	poetry run ruff check . && poetry run ruff format --check .
format:          ## Auto-fix lint + format
	poetry run ruff check --fix . && poetry run ruff format .
typecheck:       ## mypy
	poetry run mypy src
test:            ## Unit + API tests (no Docker)
	poetry run pytest -m "not integration"
test-integration: ## Integration tests (needs Docker)
	poetry run pytest -m integration
cov:             ## Tests with coverage report
	poetry run pytest --cov --cov-report=term-missing

migrate:         ## Apply migrations (conditional)
	poetry run <migration command>

infra-up:        ## Start only infrastructure containers
	docker compose up -d --wait <infra services>
up:              ## Start the full stack
	docker compose up -d --build --wait
down:            ## Stop the stack
	docker compose down
logs:            ## Tail app logs
	docker compose logs -f app
clean:           ## Remove caches
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
```
