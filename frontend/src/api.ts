export type RecordingStatus = 'pending_upload' | 'uploaded' | 'aborted' | 'failed'

export interface Recording {
  id: string
  filename: string
  content_type: string
  size_bytes: number
  status: RecordingStatus
  failure_reason: string | null
  created_at: string
  updated_at: string
  uploaded_at: string | null
}

export interface PartUploadUrl {
  part_number: number
  url: string
  expires_at: string
}

export interface UploadPlan {
  part_size_bytes: number
  part_count: number
  url_ttl_s: number
  first_part: PartUploadUrl
}

export interface CompletedPart {
  part_number: number
  etag: string
}

export interface PresignedUrl {
  url: string
  expires_at: string
}

export interface RecordingPage {
  items: Recording[]
  next_cursor: string | null
}

export interface Health {
  status: 'ok' | 'degraded' | 'fail'
  checks: Record<string, { status: 'ok' | 'fail'; required: boolean; error: string | null }>
}

export type JobStatus = 'running' | 'completed' | 'failed'
export type StageStatus = 'pending' | 'running' | 'succeeded' | 'failed'

export interface SpeechSegment {
  start_ms: number
  end_ms: number
}

export interface TranscriptSegment {
  start_ms: number
  end_ms: number
  text: string
}

export interface Transcription {
  language: string
  language_probability: number
  text: string
  segments: TranscriptSegment[]
}

export interface Processing {
  job_id: string
  recording_id: string
  status: JobStatus
  speech_detected: boolean | null
  failure_reason: string | null
  created_at: string
  completed_at: string | null
  stages: {
    name: string
    status: StageStatus
    attempts: number
    error: string | null
    started_at: string | null
    finished_at: string | null
  }[]
  vad: {
    speech_detected: boolean
    duration_ms: number
    speech_ms: number
    speech_ratio: number
    segments: SpeechSegment[]
  } | null
  transcription: Transcription | null
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly requestId: string | null

  constructor(status: number, code: string, message: string, requestId: string | null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.requestId = requestId
  }
}

interface ErrorEnvelope {
  error?: { code?: string; message?: string; request_id?: string | null }
}

export function createApi(userId: string, fetchFn: typeof fetch = fetch) {
  async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = { 'X-Dev-User-Id': userId }
    if (body !== undefined) headers['Content-Type'] = 'application/json'

    const response = await fetchFn(`/api/v1${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
    const text = await response.text()
    const data: unknown = text ? JSON.parse(text) : null
    if (!response.ok) {
      const error = (data as ErrorEnvelope | null)?.error
      throw new ApiError(
        response.status,
        error?.code ?? 'http_error',
        error?.message ?? response.statusText,
        error?.request_id ?? response.headers.get('X-Request-ID'),
      )
    }
    return data as T
  }

  return {
    register: (body: { filename: string; content_type: string; size_bytes: number }) =>
      request<{ recording: Recording; upload: UploadPlan }>('POST', '/recordings', body),
    partUploadUrl: (id: string, partNumber: number) =>
      request<PartUploadUrl>(
        'POST',
        `/recordings/${id}/parts/${partNumber}/upload-url`,
      ),
    complete: (id: string, parts: CompletedPart[]) =>
      request<Recording>('POST', `/recordings/${id}/complete`, { parts }),
    abort: (id: string) => request<Recording>('POST', `/recordings/${id}/abort`),
    get: (id: string) => request<Recording>('GET', `/recordings/${id}`),
    list: (cursor?: string | null) =>
      request<RecordingPage>(
        'GET',
        `/recordings?limit=20${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`,
      ),
    downloadUrl: (id: string) => request<PresignedUrl>('GET', `/recordings/${id}/download-url`),
    processing: (id: string) => request<Processing>('GET', `/recordings/${id}/processing`),
  }
}

export type Api = ReturnType<typeof createApi>

export async function fetchHealth(fetchFn: typeof fetch = fetch): Promise<Health> {
  const response = await fetchFn('/health/ready')
  return (await response.json()) as Health
}
