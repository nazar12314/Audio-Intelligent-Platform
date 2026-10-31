# Backend architecture: Principles, layers, feature module anatomy

> [Index](../README.md) · **Use for:** any code in src/: layering rules, import boundaries, module layout. Placeholders are defined in the index.

## 1. Principles

1. **Ports and adapters.** Business logic depends on interfaces (`Protocol`s) that describe
   what it needs: `ConversationRepository`, `Cache`, `EventPublisher`, `LLMClient`. Concrete
   technologies (Postgres, Mongo, Redis, RabbitMQ, Kafka, OpenAI, Qdrant) live in adapters.
   With this split, a technology can be swapped and the logic tested without changing the
   logic itself.
2. **One composition root.** One function builds every adapter and service. It is the only
   place where configuration decides which implementation is used.
3. **Thin transport.** HTTP, WebSocket and message handlers translate input and output, and
   delegate the work to a service.
4. **Explicit dependencies.** A service receives the collaborators it needs through its
   constructor. It never receives a container or a global it can reach into.
5. **Fail fast, degrade on purpose.** Bad configuration stops startup. When a dependency
   goes down at runtime, the service degrades in a defined way and does not crash: a cache
   miss falls back to the source, and a broker outage buffers messages or rejects them
   clearly.
6. **Every external call is bounded.** Each call has a timeout and a retry policy with
   backoff, and is observable in logs and metrics.

---

## 2. Layers and dependency rules

```
                ┌──────────────────────────────────────────────┐
 entrypoints ──►│ api/ (HTTP, WS, SSE) · <feature>/consumers.py │  transport
                └───────────────┬──────────────────────────────┘
                                ▼
                ┌──────────────────────────────────────────────┐
                │ modules/<feature>/services   (use cases)      │  application
                └───────────────┬──────────────────────────────┘
                                ▼
                ┌──────────────────────────────────────────────┐
                │ modules/<feature>/domain  ·  ports.py         │  domain + interfaces
                └───────────────▲──────────────────────────────┘
                                │ implements
                ┌───────────────┴──────────────────────────────┐
                │ modules/<feature>/adapters · infrastructure/  │  infrastructure
                └──────────────────────────────────────────────┘
```

| Layer | May import | Must not import |
|---|---|---|
| `domain/` | `shared/`, stdlib | FastAPI, drivers, `adapters/`, `infrastructure/`, `api/` |
| `ports.py` | `domain/`, `schemas/` (if a port returns DTOs) | any concrete technology |
| `services/` | `domain/`, `ports.py`, `core/exceptions`, other features' **public services or ports** | `adapters/`, `infrastructure/`, FastAPI |
| `schemas/` | Pydantic, `domain/` | services, adapters |
| `api/` (feature routers) | `schemas/`, `services/`, `api/dependencies` | `adapters/`, drivers |
| `adapters/` | `ports.py`, `domain/`, `infrastructure/<tech>` clients | `api/`, other features' adapters |
| `infrastructure/` | drivers, `core/config` | `modules/` |
| `core/container.py` | everything | — (the one exception) |

Enforce the rules with Ruff's banned-api (`TID251`) and per-file allowances. For example:

```toml
[tool.ruff.lint.flake8-tidy-imports.banned-api]
"fastapi".msg = "transport only: keep FastAPI out of domain/services"
"sqlalchemy".msg = "persistence only: use it in adapters/ or infrastructure/"
"pymongo".msg = "persistence only: use it in adapters/ or infrastructure/"
"redis".msg = "use the Cache/SessionStore port"
"aio_pika".msg = "use the EventPublisher port"
"aiokafka".msg = "use the EventPublisher port"

[tool.ruff.lint.per-file-ignores]
"src/<package>/api/**" = ["TID251"]
"src/<package>/modules/*/api/**" = ["TID251"]
"src/<package>/modules/*/adapters/**" = ["TID251"]
"src/<package>/infrastructure/**" = ["TID251"]
"src/<package>/core/container.py" = ["TID251"]
"src/<package>/entrypoints/**" = ["TID251"]
```

The pragmatic minimum is "services never import drivers or FastAPI". If tooling such as
`import-linter` is available, it can enforce whole-layer contracts.

---

## 3. Feature module anatomy

```
modules/<feature>/
├── __init__.py          # __all__: the public service(s) and port(s) other features may use
├── api/
│   └── router.py        # <feature>_router = APIRouter(prefix="/<feature>", tags=["<feature>"])
├── schemas/             # Pydantic request/response models (the API contract)
├── domain/              # entities, value objects, invariants: plain Python / dataclasses
├── ports.py             # Protocols this feature depends on
├── services/            # use cases; one class per cohesive set of operations
├── adapters/            # one file per technology: postgres.py, mongo.py, redis.py, memory.py
└── consumers.py         # conditional: message handlers for this feature (thin, like routers)
```

- **Schemas versus domain.** Schemas define the wire format and are validated at the edge.
  Domain objects carry business invariants. Map between the two explicitly. Do not hand ORM
  or ODM models to the API.
- **Persistence models** (ORM tables, Mongo documents) are private to the adapter. Repository
  ports accept and return domain objects.
- **Cross-feature calls** go through the other feature's public service or port, which the
  container injects. Never call another feature's adapter or its tables directly. For a
  reaction that need not happen immediately, publish a domain event ([architecture §8.4](06-messaging-and-background-jobs.md)).

### Minimal example

```python
# modules/chat/ports.py
class ConversationRepository(Protocol):
    async def get(self, conversation_id: UUID, owner_id: UUID) -> Conversation | None: ...
    async def append_message(self, conversation_id: UUID, message: Message) -> None: ...

# modules/chat/services/chat_service.py
class ChatService:
    def __init__(self, conversations: ConversationRepository, llm: LLMClient,
                 retriever: Retriever, cache: Cache) -> None:
        self._conversations, self._llm, self._retriever, self._cache = conversations, llm, retriever, cache

    async def ask(self, user_id: UUID, conversation_id: UUID, question: str) -> Answer:
        conversation = await self._conversations.get(conversation_id, user_id)
        if conversation is None:
            raise NotFoundError("conversation", conversation_id)
        ...

# modules/chat/api/router.py
@chat_router.post("/{conversation_id}/messages", response_model=AnswerOut)
async def ask(conversation_id: UUID, body: AskIn,
              user: CurrentUser, chat: Annotated[ChatService, Depends(get_chat_service)]) -> AnswerOut:
    return AnswerOut.from_domain(await chat.ask(user.id, conversation_id, body.question))
```
