# 0005. Event-driven processing pipeline (Stage 2: VAD)

- **Status:** accepted
- **Date:** 2026-11-01
- **Source:** Stage 2 diagrams in the Notion architecture page

## Context

Uploaded recordings must be validated, normalized and checked for speech before
transcription. Processing is CPU-bound and slow compared with HTTP, so it has to run
outside the API and scale independently. The proposed design orchestrates with AWS Step
Functions, but the project rule is that everything runs locally with docker compose, and
Step Functions has no reliable local emulator.

## Decision

- **Choreography with a small coordinator.** A `pipeline` process consumes pipeline
  events, keeps job and stage state in Postgres, and requests the next stage. Stage
  workers take a command (`processing.vad.requested`) and answer with an event
  (`processing.vad.completed` / `.failed`). That is the same contract as a Step Functions
  task with a callback, so the coordinator can be replaced by Step Functions later
  without touching the workers.
- **SQS API everywhere.** ElasticMQ in docker compose (like RustFS for S3), Amazon SQS
  on AWS: one adapter with native visibility timeouts and DLQ redrive.
- **Transactional outbox.** Events are written in the same transaction as the state
  change; the relay in the `pipeline` process publishes them. Delivery is at least
  once, so every handler is idempotent and checks recorded state first.
- **Retries.** A failing task is not acknowledged and SQS redelivers it after the
  visibility timeout. The last allowed attempt (`MAX_ATTEMPTS`) records the failure
  itself; the DLQ (`maxReceiveCount` above that) only catches messages that crash
  consumers. Invalid audio fails immediately, without retries. Busy workers keep
  extending their message lease, so long recordings are never processed twice.
- **Time limits.** Decoding and VAD run in a child process (spawned per task) that is
  killed after `ANALYSIS_TIMEOUT_S`: a hung or crashing FFmpeg decode cannot stall or
  take down the worker, which a thread could not guarantee. Independently, every
  message has a handling cap (`HANDLER_TIMEOUT_S`); past it the lease stops being
  extended and the message is retried like any other failure.
- **Graceful shutdown.** On SIGTERM a consumer lets its in-flight long poll finish and
  releases anything it returns (visibility 0) instead of abandoning the poll, because
  SQS may still assign messages to a closed request and hide them for a whole lease.
  So `WAIT_TIME_S` must stay below the platform's stop grace period (compose: 60 s).
- **Outbox hygiene.** Published rows are deleted after `OUTBOX_RETENTION_DAYS` by a
  periodic cleanup in the `pipeline` process. A row that can never be published
  (corrupt payload, unknown destination) is logged and skipped, so it cannot block the
  rows behind it.
- **One VAD stage** validates (PyAV probe: an audio stream, a positive duration within
  `MAX_DURATION_S`), normalizes to 16 kHz mono PCM WAV (kept as `normalized.wav` for
  ASR), runs Silero VAD and stores `vad.json` next to the original.
- **Silero VAD as ONNX on onnxruntime**, not the `silero-vad` package: that package
  requires PyTorch (over 1 GB), and torchaudio has no Python 3.14 Linux wheels. The MIT
  model file is vendored; the speech-timestamp post-processing is ported from
  silero-vad 6.2.3 and checked against it. Max-speech-duration splitting is not ported
  yet; it belongs with ASR chunking.
- Audio dependencies (`av`, `onnxruntime`, `numpy`) are the `processing` extra, so the
  API image stays slim and only worker images carry them.

## Consequences

- VAD throughput scales by running more `vad-worker` processes
  (`docker compose up --scale vad-worker=N`; ECS service count on AWS).
- The coordinator is ours to maintain: branching, retries per stage, and timeouts that
  Step Functions would provide come in code as stages are added.
- A job with speech is `completed` after VAD until transcription exists; the
  coordinator will request it instead once it does.
- AWS still needs: SQS queues and DLQs (Terraform), ECS services for the workers, and
  task-role permissions for SQS and the `normalized.wav` / `vad.json` artifacts.
