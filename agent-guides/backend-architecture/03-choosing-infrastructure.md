# Backend architecture: Choosing infrastructure components

> [Index](../README.md) · **Use for:** deciding which database/cache/broker/vector store/blob store a project needs. Placeholders are defined in the index.
> **Related:** [04-service-mapping](../aws-infrastructure/foundation/04-service-mapping.md)

## 5. Choosing infrastructure components

Choose based on the access pattern, not on familiarity. Record each choice in an ADR.

| Need | Default choice | Choose instead when… |
|---|---|---|
| System of record, relational data, transactions | **PostgreSQL** (SQLAlchemy 2 async + Alembic) | — |
| Flexible or nested documents, schema varies per record, append-heavy logs | **MongoDB** (PyMongo async API / Motor, or Beanie ODM) | You need multi-entity transactions or joins: use PostgreSQL + JSONB |
| Cache, sessions, rate limits, locks, short-lived state | **Redis** | — |
| Vector similarity search (RAG) | **pgvector** if Postgres is already in use and the corpus is small to medium | Large corpus, filtering, or hybrid search: **Qdrant** / Weaviate / Milvus |
| Background jobs / task queue | **Redis-backed queue** (arq / Dramatiq / Celery) for simple jobs | You need routing, DLQs, or multiple consumer services: RabbitMQ |
| Commands and work distribution between services | **RabbitMQ** (aio-pika) | — |
| Event streaming, replay, high throughput, many independent consumers | **Kafka** (aiokafka) | Low volume, or you need no replay: RabbitMQ |
| Files and blobs (uploads, documents) | **S3-compatible object storage** (local: MinIO) behind a `BlobStore` port | Small dev setup: the local filesystem adapter |
| Full-text search | Postgres FTS | Heavy search with relevance tuning: OpenSearch / Elasticsearch |

**Rules for any component:**

1. Write a port in the feature (or in `core/ports.py` when several features use it).
2. Put the shared client and its lifecycle (connect, health, close) in
   `infrastructure/<tech>/`.
3. Implement the port in `modules/<feature>/adapters/<tech>.py`.
4. Write an in-memory fake in `tests/fakes/`.
5. Add a settings group, the env keys in `.env.example`, a compose service, and a readiness
   check.
6. Add integration tests against the real technology ([architecture §11](09-api-design.md)).
