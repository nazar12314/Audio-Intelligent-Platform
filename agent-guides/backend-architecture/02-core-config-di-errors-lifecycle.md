# Backend architecture: Core: configuration, composition root, errors, lifecycle

> [Index](../README.md) · **Use for:** writing core/config.py, core/container.py, exceptions, app factory, startup/shutdown. Placeholders are defined in the index.

## 4. Core: config, container, errors, lifecycle

### 4.1 Configuration (`core/config.py`)

```python
class PostgresSettings(BaseModel):
    dsn: SecretStr
    pool_size: int = 10

class RedisSettings(BaseModel):
    url: SecretStr = SecretStr("redis://redis:6379/0")
    default_ttl_s: int = 300

class Settings(BaseSettings):
    env: Literal["dev", "test", "prod"] = "dev"
    jwt_secret: SecretStr                         # REQUIRED: no default
    postgres: PostgresSettings | None = None      # None means the component is not used
    redis: RedisSettings | None = None
    model_config = SettingsConfigDict(
        env_prefix="<APP>_", env_nested_delimiter="__",
        env_file=(Path(__file__).resolve().parents[3] / ".env",), extra="ignore",
    )

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- `core/config.py` is the only place that reads the environment. There is **one nested group
  per infrastructure component**. A group that is optional and absent turns that component
  off.
- Secrets are typed as `SecretStr` and have no default. Validate their format as well (length,
  scheme). Whatever value a validator accepts must also be usable for real.
- Turn derived and `auto` values into properties on `Settings`, so that callers never branch
  themselves.
- When `main()` hits a `ValidationError`, it prints one line per bad field and exits with a
  non-zero code, before any socket is opened.

### 4.2 Composition root (`core/container.py`)

```python
@dataclass
class Container:
    settings: Settings
    resources: AsyncExitStack           # every opened client is registered here and closed on shutdown
    chat_service: ChatService
    auth_service: AuthService
    ...

async def build_container(settings: Settings) -> Container:
    stack = AsyncExitStack()
    redis = await stack.enter_async_context(redis_client(settings.redis)) if settings.redis else None
    cache: Cache = RedisCache(redis) if redis else NullCache()
    conversations = MongoConversationRepository(mongo_db) if ... else PostgresConversationRepository(sessionmaker)
    ...
    return Container(settings=settings, resources=stack, chat_service=ChatService(conversations, llm, retriever, cache), ...)
```

- This is the **only** place where `settings` chooses an implementation: a real adapter, a
  `Null*` object when the component is disabled, or a `Fake*` in tests.
- An **optional subsystem** gets a null object (`NullCache`, `NullPublisher`), so callers never
  write `if cache is not None`.
- Import an optional heavy dependency lazily, inside its branch. An image built without that
  dependency then still starts.
- The API reaches services through small dependency functions:
  `def get_chat_service(request: Request) -> ChatService: return request.app.state.container.chat_service`.
  In tests, override them with `app.dependency_overrides`.

### 4.3 Errors (`core/exceptions.py`)

```python
class AppError(Exception):
    status_code = 500
    code = "internal_error"                     # stable, machine-readable

class NotFoundError(AppError):      status_code, code = 404, "not_found"
class ConflictError(AppError):      status_code, code = 409, "conflict"
class ValidationFailed(AppError):   status_code, code = 422, "validation_failed"
class Unauthorized(AppError):       status_code, code = 401, "unauthorized"
class Forbidden(AppError):          status_code, code = 403, "forbidden"
class RateLimited(AppError):        status_code, code = 429, "rate_limited"
class DependencyUnavailable(AppError): status_code, code = 503, "dependency_unavailable"
```

- Services raise `AppError` subclasses. They never raise `HTTPException`.
- Adapters translate driver exceptions (`DuplicateKeyError`, `IntegrityError`, timeouts)
  into these errors. No driver exception leaks above the adapter.
- One exception handler renders every error in the same format:
  `{"error": {"code": "...", "message": "...", "request_id": "..."}}`.
- A catch-all handler logs the traceback and returns a generic 500. The response never
  contains internal details.
- Message consumers map errors to delivery outcomes instead of HTTP statuses ([architecture §8.3](06-messaging-and-background-jobs.md)).

### 4.4 Lifecycle (`api/app.py` and `entrypoints/`)

```python
def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        container = await build_container(settings)
        app.state.container = container
        async with container.resources:          # closes clients in reverse order
            await container.startup()            # e.g. ensure indexes/topics, warm caches, start background tasks
            yield
            await container.shutdown()           # stop consumers, drain, flush (each step under a timeout)

    app = FastAPI(lifespan=lifespan, title="<service>")
    install_middleware(app, settings)            # request id, CORS, logging, metrics
    install_exception_handlers(app)
    app.include_router(build_api_router(settings))
    return app
```

- `entrypoints/api.py` runs `create_app()` under Uvicorn. `entrypoints/worker.py` builds the
  same container and runs consumers or scheduled jobs. Both are the same codebase and image,
  run as separate processes.
- Keep a reference to every background task, and cancel and await it on shutdown. A
  long-running loop runs under a supervisor that catches exceptions, logs them, backs off,
  and restarts the loop. The loop never dies silently.
- Shutdown order: stop accepting new work, then drain work in flight with a timeout, then
  close clients.
