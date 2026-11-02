import { describe, expect, it } from 'vitest'
import type { Processing, Recording } from './api'
import { activeSegmentIndex, formatLabel, pipelineSteps } from './derive'

const recording = (overrides: Partial<Recording> = {}): Recording => ({
  id: 'rec-1',
  filename: 'standup.wav',
  content_type: 'audio/wav',
  size_bytes: 1000,
  status: 'uploaded',
  failure_reason: null,
  created_at: '2026-11-01T10:00:00Z',
  updated_at: '2026-11-01T10:00:05Z',
  uploaded_at: '2026-11-01T10:00:05Z',
  ...overrides,
})

const processing = (
  vad: Partial<Processing['stages'][number]>,
  extra: Partial<Processing> = {},
): Processing => ({
  job_id: 'job-1',
  recording_id: 'rec-1',
  status: 'running',
  speech_detected: null,
  failure_reason: null,
  created_at: '2026-11-01T10:00:06Z',
  completed_at: null,
  stages: [
    { name: 'vad', status: 'pending', attempts: 0, error: null, started_at: null, finished_at: null, ...vad },
  ],
  vad: null,
  transcription: null,
  ...extra,
})

const states = (r: Recording, p: Processing | null) => pipelineSteps(r, p).map((s) => s.state)

describe('pipelineSteps', () => {
  it('shows an upload in progress with everything after it waiting', () => {
    expect(states(recording({ status: 'pending_upload', uploaded_at: null }), null)).toEqual([
      'active',
      'waiting',
      'waiting',
      'waiting',
    ])
  })

  it('queues validation once uploaded, before the job exists', () => {
    expect(states(recording(), null)).toEqual(['done', 'active', 'waiting', 'waiting'])
  })

  it('marks validation and detection active while VAD runs', () => {
    expect(states(recording(), processing({ status: 'running' }))).toEqual([
      'done',
      'active',
      'active',
      'waiting',
    ])
  })

  it('reports the number of speech segments when done', () => {
    const done = processing(
      { status: 'succeeded', finished_at: '2026-11-01T10:00:09Z' },
      {
        status: 'running',
        speech_detected: true,
        vad: {
          speech_detected: true,
          duration_ms: 9000,
          speech_ms: 6000,
          speech_ratio: 0.6667,
          segments: [
            { start_ms: 0, end_ms: 3000 },
            { start_ms: 4000, end_ms: 7000 },
          ],
        },
      },
    )
    const steps = pipelineSteps(recording(), done)
    expect(steps.map((s) => s.state)).toEqual(['done', 'done', 'done', 'active'])
    expect(steps[2].detail).toBe('2 speech segments')
    expect(steps[3].detail).toBe('Queued')
  })

  const afterVad = (asr: Partial<Processing['stages'][number]>, extra: Partial<Processing> = {}) => {
    const job = processing({ status: 'succeeded' }, { speech_detected: true, ...extra })
    job.stages.push({
      name: 'asr',
      status: 'pending',
      attempts: 0,
      error: null,
      started_at: null,
      finished_at: null,
      ...asr,
    })
    return pipelineSteps(recording(), job)[3]
  }

  it('follows transcription while it runs and retries', () => {
    expect(afterVad({ status: 'running', attempts: 1 })).toMatchObject({
      state: 'active',
      detail: 'Transcribing speech',
    })
    expect(afterVad({ status: 'running', attempts: 2 }).detail).toBe('Transcribing speech · attempt 2')
  })

  it('shows the language and segment count once transcribed', () => {
    const step = afterVad(
      { status: 'succeeded' },
      {
        status: 'completed',
        transcription: {
          language: 'uk',
          language_probability: 0.97,
          text: 'Привіт. Як справи?',
          segments: [
            { start_ms: 0, end_ms: 900, text: 'Привіт.' },
            { start_ms: 1200, end_ms: 2000, text: 'Як справи?' },
          ],
        },
      },
    )
    expect(step).toMatchObject({ state: 'done', detail: 'Ukrainian · 2 segments' })
  })

  it('shows transcription errors', () => {
    expect(afterVad({ status: 'failed', error: 'gave up after 3 attempts' })).toMatchObject({
      state: 'failed',
      detail: 'gave up after 3 attempts',
    })
  })

  it('skips transcription when there is no speech', () => {
    const silent = processing(
      { status: 'succeeded' },
      { status: 'completed', speech_detected: false },
    )
    expect(pipelineSteps(recording(), silent)[3]).toMatchObject({
      state: 'waiting',
      detail: 'Skipped — no speech',
    })
  })

  it('shows the processing error on validation', () => {
    const failed = processing({ status: 'failed', error: 'invalid audio: no audio stream' })
    const steps = pipelineSteps(recording(), failed)
    expect(steps[1]).toMatchObject({ state: 'failed', detail: 'invalid audio: no audio stream' })
  })

  it('flags uploads that were never queued for processing', () => {
    const steps = pipelineSteps(recording(), null, true)
    expect(steps[1]).toMatchObject({ state: 'failed', detail: 'Not processed — upload it again' })
  })

  it('shows failed uploads with their reason', () => {
    const steps = pipelineSteps(recording({ status: 'failed', failure_reason: 'size mismatch' }), null)
    expect(steps[0]).toMatchObject({ state: 'failed', detail: 'size mismatch' })
  })
})

describe('activeSegmentIndex', () => {
  const lines = [
    { start_ms: 1000, end_ms: 2000, text: 'a' },
    { start_ms: 2500, end_ms: 4000, text: 'b' },
  ]

  it('finds the line being played, or none in a pause', () => {
    expect([0, 1000, 1999, 2000, 2600, 4000].map((ms) => activeSegmentIndex(lines, ms))).toEqual([
      -1, 0, 0, -1, 1, -1,
    ])
    expect(activeSegmentIndex([], 0)).toBe(-1)
  })
})

describe('helpers', () => {
  it('labels formats from content types', () => {
    expect(['audio/mpeg', 'audio/x-wav', 'audio/mp4', 'audio/opus'].map(formatLabel)).toEqual([
      'MP3',
      'WAV',
      'M4A',
      'OPUS',
    ])
  })

})
