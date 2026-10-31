# 0001. Stage 1 (audio ingestion) architecture

- **Status:** accepted
- **Date:** 2026-10-31
- **Source:** [Audio Intelligence Platform Architecture](https://app.notion.com/p/40ac7476f70f809c8c81cc119764b06a) (Notion)

## Context

Stage 1 lets users upload audio recordings, which later trigger asynchronous processing
(Stage 2) and agentic querying (Stage 3). Audio files are large. They must land under a
per-user prefix, and their metadata must be registered and validated before processing starts.

## Decision

| Concern | Choice |
|---|---|
| API | FastAPI, Python 3.14 (stdlib `uuid.uuid7()` for time-sortable, app-generated IDs) |
| System of record | PostgreSQL 18, SQLAlchemy 2 async + asyncpg, Alembic migrations run by a one-shot `migrate` process |
| Audio storage | S3 behind the `AudioObjectStorage` port; one client per process via aioboto3 |
| Upload path | **S3 multipart upload with presigned part URLs.** Audio bytes never pass through the API |

Upload flow (from the Notion sequence diagram):

1. `POST` initialize upload → validate the request, create a `Recording` (`pending_upload`),
   `CreateMultipartUpload`, then return `recording_id`, `upload_id` and the part settings.
2. For each chunk: the client asks the API for a presigned `UploadPart` URL, then `PUT`s the
   chunk directly to S3 and keeps the returned `ETag`.
3. `POST` complete upload (part numbers + ETags) → `CompleteMultipartUpload`, then `HEAD` the
   object to verify size and type, then mark the recording `uploaded` (or `failed`), then respond.

Object keys are `users/{owner_id}/recordings/{recording_id}/original`. They are built only from
server-side IDs; the client's filename is stored as metadata only.

Status lifecycle: `pending_upload → uploaded | aborted | failed`. All three end states are
terminal in Stage 1; Stage 2 adds processing states after `uploaded`.

## Consequences

- The API stays light: no large request bodies, no streaming through the app.
- Browser clients need bucket CORS that allows `PUT` from the app origin and exposes the
  `ETag` header.
- Presigned URLs must be signed for the host the **client** reaches. When the API's internal
  S3 endpoint differs from the public one (as in docker compose: `rustfs:9000` vs
  `localhost:9000`), presigning needs a client configured with the public endpoint.
- Abandoned multipart uploads cost storage. On AWS, a bucket lifecycle rule aborts incomplete
  multipart uploads after 7 days. An abort endpoint and a cleanup job for stale
  `pending_upload` records are needed.
- Stage 2 starts processing from the `uploaded` transition (S3 event → SQS, or an outbox
  event). Never by polling the bucket.
- Authentication is not decided yet. Every recording endpoint must resolve an `owner_id`
  from an authenticated principal, and repositories filter on it inside their queries.
