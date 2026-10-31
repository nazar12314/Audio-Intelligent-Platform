# Backend architecture: Anti-patterns

> [Index](../README.md) · **Use for:** reviewing a design or code change. Placeholders are defined in the index.

## 15. Anti-patterns

| Anti-pattern | Do instead |
|---|---|
| Services importing drivers, the ORM, or FastAPI | Ports in services, technology in adapters |
| Passing the container (or `app`) into services | Explicit constructor dependencies |
| `if settings.x:` branches spread through the code | Choose the implementation once in the container; use null objects |
| Raising `HTTPException` from services; driver exceptions leaking upward | `AppError` hierarchy; adapters translate errors |
| ORM or ODM models returned from endpoints | Map to response schemas |
| Ownership filtered after a query or vector search | Filter inside the query |
| Redis as the only copy of important data | A database is the system of record; Redis holds derived and ephemeral data |
| Cache keys without a TTL or version | `<app>:<feature>:<entity>:<id>:v<n>` with TTL + jitter |
| Publishing an event right after a DB commit and hoping | Transactional outbox |
| Acking a message before processing; non-idempotent handlers | Ack after processing; deduplicate on event ID |
| Unbounded retries / no DLQ | Bounded backoff, then a DLQ |
| `asyncio.create_task` fire-and-forget for important work | A queue or event plus a worker |
| External calls without a timeout or retry policy | Shared client with timeouts, retries and a breaker |
| Model names, prompts or provider hard-coded in services | Config plus versioned prompt templates behind an `LLMClient` port |
| Unbounded arrays in a single Mongo document | One document per item, plus an index |
| Migrations run at import or app start in production | A separate `migrate` process |
| Tests calling real LLM or third-party APIs | Fakes, plus contract tests on adapters |
