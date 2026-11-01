# API: client contract

OpenAPI (`/docs`, `/openapi.json`) describes every endpoint. This file covers what it
cannot: the multi-step upload flow, in which the client sends audio straight to storage.

## Authentication

Until real authentication lands ([ADR 0004](docs/adr/0004-auth-port-with-dev-stub.md)),
every `/api/v1` request carries the caller's user ID:

```
X-Dev-User-Id: 0192f0c1-7d3e-7cc0-9b1a-3f2d5e8a9b10
```

A missing or malformed header returns `401`.

## Uploading a recording

```
1. POST /api/v1/recordings                                → recording + upload plan
                                                            (includes part 1's URL)
2. for n in 1..part_count:
     POST /api/v1/recordings/{id}/parts/{n}/upload-url    → presigned URL (n ≥ 2)
     PUT <url> with bytes [(n-1)·part_size, n·part_size)  → keep the ETag response header
3. POST /api/v1/recordings/{id}/complete {parts: [{part_number, etag}]}
                                                          → status uploaded | failed
```

1. **Register:** `{"filename", "content_type", "size_bytes"}`. `size_bytes` must be the
   exact file size. The response's `upload` holds `part_size_bytes`, `part_count`,
   `url_ttl_s` and `first_part` (`{part_number, url, expires_at}`), so a file that fits
   in one part needs no further URL request.
2. **Upload parts:** every part except the last is exactly `part_size_bytes`; the last
   is the remainder. Each URL is signed for its part's exact size, so storage answers
   any other body size with `403 SignatureDoesNotMatch`. URLs expire after `url_ttl_s`;
   request a new one to retry a part. Parts can be uploaded in parallel. Browsers must
   read the `ETag` response header (storage exposes it via CORS).
3. **Complete:** send every part with its ETag. The API asks storage to assemble the
   file, checks its size, and returns the recording:
   - `uploaded`: done;
   - `failed`, with `failure_reason`: the stored size differed, or the upload expired.
     The stored data is deleted; register the file again.

   Repeating `complete` after success returns the same recording.

`POST /api/v1/recordings/{id}/abort` cancels an upload in progress and deletes anything
already stored for it.
`GET /api/v1/recordings/{id}` returns the recording and its status.

## Processing

After a successful `complete`, the recording is processed asynchronously.
`GET /api/v1/recordings/{id}/processing` returns the job (`404` until it exists, which
is usually within a second or two):

- `status`: `running`, `completed` or `failed` (with `failure_reason`).
- `speech_detected`: set when VAD has finished.
- `stages`: per stage `status` (`pending`, `running`, `succeeded`, `failed`), `attempts`
  and the last `error`.
- `vad`: once VAD succeeded, `duration_ms`, `speech_ms`, `speech_ratio` and `segments`
  (`[{start_ms, end_ms}]`, times in the original recording).

## Listing and downloading

- `GET /api/v1/recordings?limit=20&cursor=…` lists your recordings, newest first. Pass
  the response's `next_cursor` to get the next page; it is `null` on the last page.
- `GET /api/v1/recordings/{id}/download-url` returns `{"url", "expires_at"}` for an
  `uploaded` recording (`409` otherwise). `GET` the URL directly from storage.

| Status | Meaning |
|---|---|
| `pending_upload` | Registered; parts may be uploaded |
| `uploaded` | Stored and verified |
| `failed` | Completed but not verifiable (see `failure_reason`) |
| `aborted` | Cancelled by the client |

## Errors

Every error uses one envelope:
`{"error": {"code", "message", "request_id", "details"?}}`.

| Status | `code` | When |
|---|---|---|
| 401 | `unauthorized` | Missing or invalid user header |
| 404 | `not_found` | Unknown recording, or another user's |
| 409 | `conflict` | Operation does not fit the status (e.g. upload URL after abort) |
| 422 | `validation_failed` | Bad input, unsupported type, too large, wrong part list or ETag |
| 503 | `dependency_unavailable` | Database or storage unreachable; retry later |

## Events

Messages use one envelope: `{"id", "type", "version", "occurred_at", "correlation_id",
"data"}`. `correlation_id` is the request ID that started the chain. Consumers
deduplicate by checking recorded state, because delivery is at least once.

| Type (v1) | Producer → consumer | Queue | `data` |
|---|---|---|---|
| `recordings.recording.uploaded` | API (`complete`) → coordinator | pipeline-events | `recording_id`, `owner_id`, `object_key`, `content_type`, `size_bytes` |
| `processing.vad.requested` | coordinator → VAD workers | vad-tasks | `job_id` |
| `processing.vad.completed` | VAD worker → coordinator | pipeline-events | `job_id`, `speech_detected` |
| `processing.vad.failed` | VAD worker → coordinator | pipeline-events | `job_id`, `error` |
