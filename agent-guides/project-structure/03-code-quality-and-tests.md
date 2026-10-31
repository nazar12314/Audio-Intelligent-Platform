# Project structure: Linting, type checking, pre-commit, test scaffold

> [Index](../README.md) · **Use for:** configuring Ruff/mypy/pre-commit or pytest/coverage. Placeholders are defined in the index.
> **Related:** [01-principles-and-layers](../backend-architecture/01-principles-and-layers.md), [11-testing](../backend-architecture/11-testing.md)

## 4. Linting, formatting, type checking

```toml
[tool.ruff]
target-version = "py313"
line-length = 120
src = ["src", "tests"]
extend-exclude = ["migrations"]
force-exclude = true                 # honour excludes when pre-commit passes explicit paths

[tool.ruff.lint]
select = [
    "E", "W", "F",    # pycodestyle, pyflakes
    "I",              # isort
    "B",              # bugbear
    "C4",             # comprehensions
    "UP",             # pyupgrade
    "SIM",            # simplify
    "ASYNC",          # async pitfalls
    "S",              # bandit-lite security checks
    "TID",            # tidy imports (banned-api for architecture boundaries)
    "RUF",
]
ignore = ["B008"]                    # FastAPI Depends() in argument defaults

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101", "S105", "S106"]   # asserts and fake secrets are fine in tests

[tool.ruff.lint.isort]
known-first-party = ["<package>"]

[tool.ruff.format]
quote-style = "double"
docstring-code-format = true

[tool.mypy]
python_version = "3.13"
strict = true
plugins = ["pydantic.mypy"]
mypy_path = "src"

[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false
```

- Ruff lints the tests too. Use per-file ignores where tests need different rules; never
  exclude `tests/`.
- Import boundaries between layers are enforced with Ruff's `flake8-tidy-imports` banned-api
  rules. The rules themselves are listed in [architecture §2](../backend-architecture/01-principles-and-layers.md).

### `.pre-commit-config.yaml`

```yaml
exclude: ^migrations/
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-toml
      - id: check-added-large-files
      - id: detect-private-key
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.4                      # must match the ruff version in pyproject
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/python-poetry/poetry
    rev: 2.0.1
    hooks:
      - id: poetry-check
        args: [--lock]
```

---

## 5. Tests scaffold

```toml
[tool.pytest.ini_options]
addopts = "-ra -q --tb=short --strict-markers"
testpaths = ["tests"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
markers = [
    "integration: needs real infrastructure (Docker); run with `make test-integration`",
]

[tool.coverage.run]
source = ["src/<package>"]
branch = true

[tool.coverage.report]
fail_under = 80
show_missing = true
```

- `make test` runs the unit and API tests: fast, no Docker. `make test-integration` runs the
  tests marked `integration`. CI runs both.
- Settings must not be read at import time. Tests then configure the environment with
  `monkeypatch.setenv` plus a cache clear, and need no bootstrap `conftest.py` at the root.
- Any fake secrets in tests are obviously fake (`"test-" + "x" * 32`), yet still pass the
  real validation.
