# Project structure: Setup checklist

> [Index](../README.md) · **Use for:** bootstrapping a new project end to end (start here for a new repo). Placeholders are defined in the index.

## 12. Setup checklist

1. Create the skeleton from [structure §2](01-toolchain-and-layout.md), including only the conditional folders the project needs.
2. Write `pyproject.toml` ([structure §3](02-dependencies-and-lockfiles.md)–[structure §5](03-code-quality-and-tests.md), [structure §10](06-ci-releases-and-docs.md)) and run `poetry lock`. Commit `pyproject.toml` and the
   lock file together.
3. Add `.gitignore`, `.editorconfig`, `.python-version`, `.pre-commit-config.yaml`, and the
   allow-list `.dockerignore`.
4. Write `.env.example`, listing every setting and leaving secrets blank.
5. Add the `Makefile` ([structure §7](04-env-files-and-makefile.md)).
6. Add `docker/app/Dockerfile` and `docker-compose.yml` with only the required infrastructure
   ([structure §8](05-docker-and-local-infra.md)–[structure §9](05-docker-and-local-infra.md)).
7. Lay out the code inside `src/<package>/` following
   [architecture §1](../backend-architecture/01-principles-and-layers.md)–[architecture §4](../backend-architecture/02-core-config-di-errors-lifecycle.md). Start with `core/config.py`, the app
   factory, and a health endpoint.
8. Add `tests/conftest.py` and a first test for the health endpoint.
9. Add the CI pipeline ([structure §10](06-ci-releases-and-docs.md)).
10. Write `README.md` and seed `CHANGELOG.md`.
11. Verify all of the following:
    - `make setup && make lint && make typecheck && make test` passes;
    - `make up` starts the stack and every container is healthy;
    - `curl localhost:8000/health/ready` returns 200;
    - the app refuses to start when a required secret is missing.
