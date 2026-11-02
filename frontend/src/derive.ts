import type { Processing, Recording, RecordingStatus, TranscriptSegment } from './api'
import { languageName } from './format'

export type StepState = 'done' | 'active' | 'failed' | 'waiting'

export interface PipelineStep {
  title: string
  detail: string
  state: StepState
}

const FORMATS: Record<string, string> = {
  'audio/aac': 'AAC',
  'audio/flac': 'FLAC',
  'audio/x-flac': 'FLAC',
  'audio/mp4': 'M4A',
  'audio/x-m4a': 'M4A',
  'audio/mpeg': 'MP3',
  'audio/ogg': 'OGG',
  'audio/wav': 'WAV',
  'audio/wave': 'WAV',
  'audio/x-wav': 'WAV',
  'audio/webm': 'WEBM',
}

export function formatLabel(contentType: string): string {
  return FORMATS[contentType] ?? contentType.split('/').pop()?.toUpperCase() ?? 'AUDIO'
}

export const STATUS_LABELS: Record<RecordingStatus, string> = {
  pending_upload: 'Uploading',
  uploaded: 'Uploaded',
  failed: 'Failed',
  aborted: 'Aborted',
}

export function pipelineSteps(
  recording: Recording,
  processing: Processing | null,
  notProcessed = false,
): PipelineStep[] {
  const upload: PipelineStep = {
    pending_upload: { title: 'Upload', detail: 'Uploading to storage', state: 'active' },
    uploaded: { title: 'Upload', detail: 'Stored and size-verified', state: 'done' },
    failed: { title: 'Upload', detail: recording.failure_reason ?? 'Upload failed', state: 'failed' },
    aborted: { title: 'Upload', detail: 'Upload aborted', state: 'failed' },
  }[recording.status] as PipelineStep

  const vad = processing?.stages.find((stage) => stage.name === 'vad')
  const asr = processing?.stages.find((stage) => stage.name === 'asr')
  let validation: PipelineStep = { title: 'Validation', detail: 'Format check, 16 kHz mono', state: 'waiting' }
  let speech: PipelineStep = { title: 'Speech detection', detail: 'Silero VAD', state: 'waiting' }
  let transcription: PipelineStep = { title: 'Transcription', detail: 'Faster-Whisper', state: 'waiting' }

  if (recording.status === 'uploaded') {
    if (notProcessed) {
      validation = { ...validation, detail: 'Not processed — upload it again', state: 'failed' }
    } else if (!vad || vad.status === 'pending') {
      validation = { ...validation, detail: 'Queued', state: 'active' }
    } else if (vad.status === 'running') {
      validation = { ...validation, detail: 'Validating and normalizing', state: 'active' }
      speech = { ...speech, state: 'active' }
    } else if (vad.status === 'failed') {
      validation = { ...validation, detail: vad.error ?? 'Processing failed', state: 'failed' }
    } else {
      validation = { ...validation, detail: 'Normalized to 16 kHz mono', state: 'done' }
      const segments = processing?.vad?.segments.length ?? 0
      speech = {
        ...speech,
        detail: segments ? `${segments} speech segment${segments === 1 ? '' : 's'}` : 'No speech found',
        state: 'done',
      }
      transcription = transcriptionStep(transcription, processing, asr)
    }
  }

  return [upload, validation, speech, transcription]
}

function transcriptionStep(
  step: PipelineStep,
  processing: Processing | null,
  asr: Processing['stages'][number] | undefined,
): PipelineStep {
  if (processing?.speech_detected === false) return { ...step, detail: 'Skipped — no speech' }
  if (!asr || asr.status === 'pending') return { ...step, detail: 'Queued', state: 'active' }
  if (asr.status === 'running') {
    const retry = asr.attempts > 1 ? ` · attempt ${asr.attempts}` : ''
    return { ...step, detail: `Transcribing speech${retry}`, state: 'active' }
  }
  if (asr.status === 'failed') {
    return { ...step, detail: asr.error ?? 'Transcription failed', state: 'failed' }
  }
  const result = processing?.transcription
  if (!result) return { ...step, detail: 'Transcribed', state: 'done' }
  const count = result.segments.length
  return {
    ...step,
    detail: `${languageName(result.language)} · ${count} segment${count === 1 ? '' : 's'}`,
    state: 'done',
  }
}

/** Index of the segment playing at `ms`, or -1 between segments. */
export function activeSegmentIndex(segments: TranscriptSegment[], ms: number): number {
  let low = 0
  let high = segments.length - 1
  let found = -1
  while (low <= high) {
    const middle = (low + high) >> 1
    if (segments[middle].start_ms <= ms) {
      found = middle
      low = middle + 1
    } else {
      high = middle - 1
    }
  }
  return found >= 0 && ms < segments[found].end_ms ? found : -1
}
