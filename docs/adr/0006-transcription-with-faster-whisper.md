# 0006. Transcription with Faster-Whisper

- **Status:** accepted
- **Date:** 2026-11-02

## Context

Recordings with speech must be transcribed, with segment timestamps and the spoken
language. VAD ([ADR 0005](0005-event-driven-processing-pipeline.md)) already stores the
normalized 16 kHz mono audio and the speech segments. Speech models are large, slow to
load and CPU- or GPU-heavy, so transcription has to scale apart from VAD.

## Decision

- **One more stage, same contract.** When VAD finds speech, the coordinator adds an
  `asr` stage and sends `processing.asr.requested` to its own queue (`asr-tasks`, with a
  DLQ). ASR workers answer with `processing.asr.completed` / `.failed`. A job without
  speech still completes after VAD. Retries, `MAX_ATTEMPTS` and idempotency work as for
  VAD; the bookkeeping both workers share is `StageTask`.
- **Faster-Whisper (CTranslate2)**, not `openai-whisper`: it needs no PyTorch, is up to
  four times faster at the same accuracy by its own benchmarks, runs int8 on CPU, and
  switches to a CUDA GPU through configuration (`AUDIO_ASR__DEVICE`,
  `AUDIO_ASR__COMPUTE_TYPE`). The model is configuration (`AUDIO_ASR__MODEL`, default
  `medium`). It ships as the `asr` extra and its own worker image.
- **No Apple GPU (MPS).** CTranslate2 supports CPU and CUDA only (`unsupported device
  mps`), and containers on macOS cannot reach Metal anyway. MLX (`mlx-whisper`) does
  run on the Apple GPU: `medium` on an M4 transcribed at a real-time factor of 0.17,
  against 0.25 for the batched CPU path here. It would be another adapter behind
  `SpeechTranscriber`, for workers run on the host only, if local throughput matters.
- **The model loads once per worker process**, when the worker starts, and stays in
  memory. Downloads go to the Hugging Face cache (a volume in compose), so restarts and
  replicas do not download again.
- **Only speech is transcribed, in batches.** The worker packs consecutive VAD speech
  segments into windows of at most 20 s of the recording (`speech_windows`; longer
  segments are cut into equal pieces) and decodes `AUDIO_ASR__BATCH_SIZE` windows
  together with Faster-Whisper's batched pipeline: on the M4 CPU with `medium` int8,
  about twice as fast as sequential decoding. VAD runs once, and long silences are
  never decoded, so they cannot produce hallucinated text. Windows are independent, so
  text is not conditioned on the previous window.
- **20 s windows, not 30 s.** Whisper hears 30 s at a time. When speech fills nearly
  all of it, Whisper leaves the last sentence unfinished; sequential decoding comes
  back for it, a batched decode drops it. With 30 s windows a 3-minute test recording
  lost 19 of 552 words; with 20 s none, at the same speed as 30 s windows plus a second
  pass. Speech of at least 1 s at a window's end that still gets no words is decoded
  again on its own (`unheard_window_ends`); shorter bursts are mostly breaths whose text
  was dropped as hallucinated, and decoding them again cost 13% more time for nothing.
- **Segments both stages agree on.** Whisper decodes with word timestamps. Every word
  is mapped into its Whisper segment's window (a word's own timing can stray a few ms
  into the previous window) and placed into the VAD segment it was spoken in. VAD
  segments are then joined while the text before a pause does not end a sentence
  (`.?!…` and CJK marks) and the pause is at most 1.5 s. A transcript segment is
  therefore whole VAD segments holding whole sentences, with VAD's bounds, and the UI
  highlights the same segments on the waveform and in the transcript. Whisper's own
  segments are phrases, so they are not used as boundaries, and a pause threshold
  alone cannot find sentences: pauses inside and between sentences overlap (100–700 ms
  on the test recordings). `vad.json` keeps every pause. Word timestamps cost about 30%
  more decoding time.
- **Hallucinations are dropped.** Batched decoding skips Whisper's usual "no speech"
  check, so text over noise VAD let through survives ("Thanks for watching!" over a
  grunt). A Whisper segment is dropped when its window's `no_speech_prob` exceeds 0.6
  (Whisper's own threshold) or when none of its words reaches probability 0.5. On a
  13-minute gym video, real speech stayed at or below 0.39 and always had a confident
  word. The VAD segment stays, with empty text.
- **The language** is detected per recording unless `AUDIO_ASR__LANGUAGE` forces one.
  The detected language and its probability are stored.
- **Output.** Two artifacts next to the original. `transcript.json` (version 3) holds
  the language, the full text, the model name and the segments (`start_ms`, `end_ms`,
  `text`): what the API serves. `words.json` holds each segment's words with their
  times and probabilities, kept for diarization and word-level playback; apart, it
  stays out of every API read (several MB for a long recording). The stage result in
  Postgres keeps a summary and both keys.
- **Time limit in a thread, not a child process.** Unlike VAD, the input is our own
  normalized WAV, so there is no untrusted FFmpeg decode to isolate, and a child process
  per task would reload the model every time. Transcription runs in a worker thread and
  checks between decoded batches (each covers at most `BATCH_SIZE` × 20 s) whether
  `AUDIO_ASR__TRANSCRIPTION_TIMEOUT_S` has passed or the handler was cancelled, then
  stops. `HANDLER_TIMEOUT_S` must exceed it.

## Consequences

- ASR throughput scales with `asr-worker` replicas, independently of VAD. Each replica
  holds one model in memory: a `medium` int8 worker measured 2.3 GB after transcribing
  a 3-minute recording (the download is ~1.5 GB).
- A recording that keeps hitting the time limit only fails after every attempt has
  used it up: with the defaults about 2.5 h (3 × (3000 s + a 60 s lease)), during
  which one worker is busy with it. A limit that scales with the recording's speech
  duration would end such cases sooner.
- When ASR fails, the job fails, but the VAD stage's result and artifacts stay and the
  API still returns the speech segments. A "completed with errors" status could
  separate this from a job that produced nothing.
- A crash inside CTranslate2 takes the worker process down; the message is redelivered
  and eventually lands in the DLQ. That is acceptable for trusted input.
- Faster-Whisper keeps the speech audio of one recording and its features in memory
  (roughly 1.5 GB for 4 hours of speech), which sets the ASR worker's memory floor.
- Speaker diarization is not produced yet; it belongs to a later stage and can use the
  stored word timings.
- AWS still needs: the `asr-tasks` queue and DLQ, an ECS service (a GPU instance if the
  model needs one), the model cache (baked into the image or on EFS), and task-role
  permissions to read `normalized.wav` / `vad.json` and write `transcript.json`.
