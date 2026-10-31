# Project structure: CI pipeline, releases, repository docs

> [Index](../README.md) · **Use for:** setting up CI stages, semantic-release, README/API.md/ADRs. Placeholders are defined in the index.
> **Related:** [cicd-deployment](../aws-infrastructure/operations/cicd-deployment.md)

## 10. CI pipeline (platform-agnostic)

| Stage | Jobs |
|---|---|
| `lint` | `poetry check --lock`, `ruff check .`, `ruff format --check .`, `mypy src` |
| `test` | `pytest -m "not integration" --cov`; `pytest -m integration` with Docker (services or testcontainers) |
| `build` | build the image; start it (`docker run … <service>-api --help` or a health probe) |
| `scan`  | dependency audit (`pip-audit`), image scan (e.g. Trivy), secret scan |
| `release` | on the main branch only: `semantic-release version` (bump, tag, changelog), then push the image |

- CI installs from the lock file with caching keyed on the hash of the lock file.
- CI runs the **whole** test suite, never a hand-picked subset.
- CI never auto-fixes code. It only checks.
- Deploy jobs are outside the scope of this document (see [aws §14](../aws-infrastructure/operations/cicd-deployment.md)).

### Releases (`pyproject.toml`)

```toml
[tool.semantic_release]
version_toml = ["pyproject.toml:project.version"]
tag_format = "v{version}"
commit_message = "chore(release): {version} [skip ci]"
allow_zero_version = true            # false once 1.0.0 is cut

[tool.semantic_release.branches.main]
match = "main"

[tool.semantic_release.changelog]
mode = "update"
insertion_flag = "<!-- version list -->"

[tool.semantic_release.commit_parser_options]
minor_tags = ["feat"]
patch_tags = ["fix", "perf"]
parse_squash_commits = true
```

Commits follow Conventional Commits, with the feature module as the scope:
`feat(chat): stream partial answers`, `fix(deps): …`.

---

## 11. Repository docs

- **README.md:**
  - what the service is;
  - an architecture sketch (links to architecture docs or ADRs);
  - prerequisites;
  - quick start, both `make setup && make infra-up && make run` and `make up`;
  - a configuration overview;
  - the list of Makefile targets;
  - the testing approach;
  - the release process.
- **API.md:** the client contract, needed when OpenAPI alone does not cover it (WebSocket or
  SSE message types, event schemas, auth flow). Update it in the same change as the endpoint.
- **docs/adr/:** one Architecture Decision Record per significant choice, for example
  "MongoDB over PostgreSQL for conversations" or "RabbitMQ for ingestion jobs".
- **CHANGELOG.md:** generated. Seed it with `# Changelog` and `<!-- version list -->`.
- **Comments** explain *why*: the constraint, the past incident, the trade-off. A version pin
  or ceiling always gets a comment with its reason.
- Each repo uses one language for its docs and comments.
