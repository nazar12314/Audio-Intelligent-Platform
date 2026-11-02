# Frontend

The sonar. workspace (React + Vite): upload audio through presigned multipart URLs, play
it back from storage with speech segments highlighted, read its transcript, and follow
processing live.

```bash
make up           # backend + Postgres + RustFS (repo root)
make fe-install   # once
make fe-dev       # http://localhost:5173
```

- `/api` and `/health` are proxied to `http://localhost:8000` (override with `API_URL`).
- Parts go straight from the browser to storage. The bucket's CORS rules allow
  `http://localhost:5173` and expose `ETag`, so the dev server must run on that port.
- The dev user ID is sent as `X-Dev-User-Id`; switch it from the avatar menu ("New user"
  is a quick way to check that recordings are private to their owner), or open
  `http://localhost:5173/?user=<uuid>` to share a workspace between browsers.
- Uploaded recordings show their stored waveform with the VAD speech segments highlighted;
  the inspector follows the processing pipeline live (validation, speech detection,
  transcription).
- Once transcribed, the transcript lists timestamped lines with the detected language.
  Clicking a line plays the recording from there; the line being played is highlighted.

`make fe-check` runs lint (oxlint), unit tests (Vitest) and the production build.
