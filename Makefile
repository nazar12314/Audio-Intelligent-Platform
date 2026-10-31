.DEFAULT_GOAL := help
.PHONY: help setup install env hooks run lint format typecheck test test-integration cov \
        migrate migration infra-up up down logs clean

help:             ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-18s %s\n",$$1,$$2}'

setup: install env hooks  ## First-time local setup

install:          ## Install deps from the lock file
	@echo "→ installing dependencies from poetry.lock"
	poetry sync

env:              ## Create .env from .env.example (never overwrites)
	@test -f .env && echo "→ .env exists, leaving it untouched" || (cp .env.example .env && echo "→ .env created: fill in the blank secrets")

hooks:            ## Install pre-commit hooks
	@echo "→ installing pre-commit hooks"
	poetry run pre-commit install

run:              ## Run the API on the host with hot reload (needs `make infra-up`)
	@echo "→ starting API on http://localhost:8000"
	@# --env-file also exports .env to the process, so the AWS SDK's credential chain sees AWS_* keys.
	poetry run uvicorn audio_platform.entrypoints.api:app_factory --factory --reload --env-file .env

lint:             ## Check lint + format (no changes)
	@echo "→ ruff check + format check"
	poetry run ruff check . && poetry run ruff format --check .

format:           ## Auto-fix lint + format
	@echo "→ ruff fix + format"
	poetry run ruff check --fix . && poetry run ruff format .

typecheck:        ## mypy (strict on src)
	@echo "→ mypy"
	poetry run mypy

test:             ## Unit + API tests (no Docker)
	@echo "→ unit + API tests"
	poetry run pytest -m "not integration"

test-integration: ## Integration tests (needs Docker)
	@echo "→ integration tests"
	poetry run pytest -m integration

cov:              ## All tests with coverage report
	@echo "→ tests with coverage"
	poetry run pytest --cov --cov-report=term-missing

migrate:          ## Apply migrations to the database in .env
	@echo "→ alembic upgrade head"
	poetry run alembic upgrade head

migration:        ## Autogenerate a migration: make migration m="create recordings"
	@test -n "$(m)" || (echo 'usage: make migration m="short description"' && exit 1)
	@rev=$$(printf "%04d" $$(( $$(ls migrations/versions/*.py 2>/dev/null | wc -l) + 1 ))); \
	echo "→ alembic revision $$rev: $(m)"; \
	poetry run alembic revision --autogenerate --rev-id $$rev -m "$(m)"

infra-up: env     ## Start only infrastructure (Postgres, RustFS), create the bucket, apply migrations
	@echo "→ starting postgres + rustfs"
	docker compose up -d --wait postgres rustfs
	@# One-shot services run via `compose run`: `up --wait` treats their normal exit as a failure.
	@echo "→ creating bucket + applying migrations"
	docker compose run --rm s3-init
	docker compose run --rm --build migrate

up: env           ## Start the full stack
	@echo "→ starting full stack"
	docker compose up -d --build --wait

down:             ## Stop the stack
	@echo "→ stopping stack"
	docker compose down

logs:             ## Tail app logs
	docker compose logs -f app

clean:            ## Remove caches
	@echo "→ removing caches"
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage coverage.xml htmlcov
