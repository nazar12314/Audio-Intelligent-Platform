# syntax=docker/dockerfile:1
ARG PYTHON_IMAGE=python:3.14.10-slim-trixie

FROM ${PYTHON_IMAGE} AS builder
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1
WORKDIR /app
# Keep in sync with .pre-commit-config.yaml and CI.
RUN pip install "poetry==2.4.1"
COPY pyproject.toml poetry.lock README.md ./
# Optional extras, e.g. POETRY_EXTRAS=processing for the audio workers.
ARG POETRY_EXTRAS=""
# Dependency layer: cached until the lock file changes.
RUN poetry install --only main --no-root ${POETRY_EXTRAS:+--extras "$POETRY_EXTRAS"}
COPY src ./src
# Installs the project itself into .venv.
RUN poetry install --only main ${POETRY_EXTRAS:+--extras "$POETRY_EXTRAS"}

FROM ${PYTHON_IMAGE} AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app
RUN useradd --create-home --uid 10001 app
COPY --from=builder --chown=app /app/.venv ./.venv
COPY --from=builder --chown=app /app/src ./src
COPY --chown=app alembic.ini ./
COPY --chown=app migrations ./migrations
USER app
EXPOSE 8000
# Every process type: `audio-platform-api`, `audio-platform-worker <role>`, `alembic upgrade head`.
CMD ["audio-platform-api"]
