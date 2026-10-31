# Backend architecture: External APIs, LLM providers, RAG

> [Index](../README.md) · **Use for:** outbound HTTP clients, retries/circuit breakers, LLM/embedding ports, streaming, RAG ingestion/retrieval. Placeholders are defined in the index.
> **Related:** [ai-ml](../aws-infrastructure/services/ai-ml.md)

## 9. External APIs, LLM providers, retrieval

### 9.1 Outbound HTTP (all third parties)

- `infrastructure/http/` provides one shared `httpx.AsyncClient` per base URL, with explicit
  timeouts (connect, read, total), connection limits, and a `User-Agent`.
- Wrap every call in a **retry policy**: exponential backoff with jitter (for example with
  `tenacity`), applied only to idempotent or retry-safe errors (timeouts, 429, 5xx), and
  honouring `Retry-After`.
- Add a **circuit breaker** for a dependency that may be down for a long time: after N
  consecutive failures, fail fast with `DependencyUnavailable` for a cooldown period.
- Log every call with its method, host, route template, status, and latency. Never log
  headers that carry secrets.

### 9.2 LLM provider abstraction

```python
class LLMClient(Protocol):
    async def complete(self, messages: list[ChatMessage], *, params: LLMParams) -> Completion: ...
    def stream(self, messages: list[ChatMessage], *, params: LLMParams) -> AsyncIterator[CompletionChunk]: ...

class EmbeddingClient(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
```

- Each provider gets its own adapter (`adapters/anthropic.py`, `adapters/openai.py`,
  `adapters/local.py`). The provider and model are chosen in settings, and model IDs live in
  configuration, not in code.
- **Prompts are versioned assets.** Keep them as templates in `modules/<feature>/prompts/`,
  each with an ID and a version that are recorded with every answer.
- Track `input_tokens`, `output_tokens`, latency, and cost per request in metrics, and store
  them on the message record.
- Enforce a **token budget**: trim or summarize the history to fit the context window. Set a
  maximum output length and a per-user quota ([architecture §10.4](08-auth.md)).
- **Streaming to clients:** use SSE (`text/event-stream`) for one-way token streams, and
  WebSocket only for bidirectional needs. Persist the final assembled message once the stream
  completes. Handle client disconnects by cancelling the upstream call.
- Treat model output as untrusted input. Validate any structured output against a Pydantic
  schema, and never execute it or pass it to a shell or a query.

### 9.3 Retrieval (RAG)

Split RAG into two flows: **ingestion**, which is asynchronous, and **retrieval**, which runs
inside the request.

```
Ingestion (worker):  upload → BlobStore → event "rag.document.uploaded" → parse → chunk → embed → VectorStore.upsert → job status
Retrieval (request): question → (cache) → embed query → VectorStore.search(filter=tenant/owner) → (rerank) → build prompt → LLM
```

```python
class VectorStore(Protocol):
    async def upsert(self, chunks: list[Chunk]) -> None: ...
    async def search(self, vector: list[float], *, top_k: int, filters: dict[str, Any]) -> list[ScoredChunk]: ...
    async def delete_document(self, document_id: UUID) -> None: ...
```

- Every chunk stores `document_id`, `owner_id` / `tenant_id`, its position, a hash of the
  source, the **embedding model name and version**, and the chunker version. Changing the
  embedding model requires re-embedding into a new collection, followed by a switch-over.
- **Access control happens inside the vector query.** The `owner_id` / `tenant_id` filter is
  part of every search. Never filter results after retrieval.
- Ingestion is idempotent per (`document_id`, content hash). Re-uploading the same file does
  not create duplicates.
- Cache embeddings by content hash. Cache retrieval results only briefly, and only when the
  corpus changes rarely.
- Keep the retrieved chunk IDs on each answer, so that the answer can cite sources and be
  evaluated.
