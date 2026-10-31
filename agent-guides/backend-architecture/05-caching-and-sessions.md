# Backend architecture: Caching and sessions

> [Index](../README.md) · **Use for:** cache-aside, key naming, TTLs, stampede protection, auth vs conversation sessions. Placeholders are defined in the index.
> **Related:** [08-auth](08-auth.md)

## 7. Caching and sessions

### 7.1 Cache

```python
class Cache(Protocol):
    async def get(self, key: str) -> bytes | None: ...
    async def set(self, key: str, value: bytes, ttl_s: int) -> None: ...
    async def delete(self, *keys: str) -> None: ...
```

- **Cache-aside.** Read the cache. On a miss, load from the source and write the cache with a
  TTL. On a write to the source, delete the key; do not update it in place.
- **Key format:** `<app>:<feature>:<entity>:<id>:v<schema>`, for example
  `chatbot:rag:embedding:<sha256>:v1`. Bump the version suffix instead of flushing the cache.
- **Every key has a TTL.** Add jitter (±10%) so that many keys do not expire at once.
- **Stampede protection** for expensive values (LLM answers, embeddings): either take a
  short Redis lock (`SET key NX PX`), or have concurrent requests in the same process share a
  single in-flight future.
- **Serialization:** use JSON or msgpack, with a versioned shape. Never use `pickle`.
- **Failure policy:** if Redis is unavailable, log at a throttled rate and continue as if
  every lookup were a miss. A cache outage must never fail a request.
- **Deterministic cache keys for LLM and RAG:** hash the full input, including the model name,
  the prompt template version, the parameters, and the IDs of the retrieved context.
  Cache only deterministic outputs (temperature 0), or document that the cached answer is
  reused on purpose.

### 7.2 Sessions

There are two kinds of session. Keep them separate.

| Kind | What | Where |
|---|---|---|
| **Auth session** | Proof of login: a refresh token or session ID | Redis (`<app>:session:<id>`), TTL equal to the refresh lifetime; revocation list |
| **Conversation / workflow state** | Chat history, context window, in-progress state | System of record (Mongo or Postgres). A Redis hot copy is optional |

- A server-side session store sits behind a `SessionStore` port with `create`, `get`,
  `touch` (sliding TTL), `revoke`, and `revoke_all_for_user`.
- Session IDs are random (`secrets.token_urlsafe(32)`). Store only a hash of the ID when
  practical.
- When a password or role changes, revoke all of that user's sessions.
