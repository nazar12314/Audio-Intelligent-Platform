# 0002. RustFS as the local S3-compatible storage

- **Status:** accepted
- **Date:** 2026-10-31

## Context

The agent guides default to MinIO for local S3. MinIO no longer publishes community Docker
images: `minio/minio` is gone from Docker Hub. LocalStack is an alternative, but adds weight
and account requirements for a single service.

## Decision

Use **RustFS** (`rustfs/rustfs:1.0.4`, Apache-2.0) in docker compose and in integration tests.
The app treats it as plain S3 through `AUDIO_AWS__ENDPOINT_URL` with path-style addressing.
On AWS the endpoint is unset and real S3 is used. No code changes.

Verified against RustFS 1.0.4: `CreateMultipartUpload`, presigned `UploadPart` via plain HTTP
`PUT` (ETag returned), `CompleteMultipartUpload`, `HeadObject`, `AbortMultipartUpload`,
`HeadBucket`.

## Consequences

- This deviates from the guides' default (MinIO). Revisit if RustFS compatibility gaps appear.
- Port contract tests for `AudioObjectStorage` run against RustFS. Behaviour that differs from
  AWS (CORS defaults, error codes) must be checked against real S3 before production.
