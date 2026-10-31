# Backend architecture: API design conventions

> [Index](../README.md) · **Use for:** route versioning, error format, idempotency keys, pagination, SSE, OpenAPI, CORS. Placeholders are defined in the index.

## 11. API design conventions

- Prefix routes with a version: `/api/v1/...`. A breaking change means a new version, and the
  old one remains available during a deprecation window.
- Request and response models are separate and use explicit field constraints. Response
  models never expose internal fields (password hashes, internal IDs that should stay
  private).
- Errors use one format ([architecture §4.3](02-core-config-di-errors-lifecycle.md)). Validation errors (422) use the same envelope.
- **Idempotency:** a `POST` that creates something or costs money (sending a chat message,
  starting an ingestion job) accepts an `Idempotency-Key` header. The key is stored in Redis
  with the response for 24 h.
- Long operations return `202` plus a job resource. Streams use SSE ([architecture §9.2](07-external-apis-llm-rag.md)).
- OpenAPI is generated. Set `summary`, `tags` and `response_model` on every route, and
  disable `/docs` in production unless it is protected.
- CORS sets an explicit allow-list of origins from the settings; never `*` together with
  credentials.
