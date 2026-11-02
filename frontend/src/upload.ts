import type { Api, CompletedPart, Recording, UploadPlan } from './api'

export type Scenario = 'normal' | 'wrong-size' | 'wrong-etag' | 'abort-midway'

export const SCENARIOS: Record<Scenario, string> = {
  normal: 'Normal upload',
  'wrong-size': 'Declare 1 byte more than the file (expect: storage rejects the part, 403)',
  'wrong-etag': 'Send a corrupted ETag (expect: 422, upload stays open)',
  'abort-midway': 'Abort after the first part (expect: aborted)',
}

export type Stage = 'registering' | 'uploading' | 'completing' | 'aborting' | 'done'

export interface PartRange {
  partNumber: number
  start: number
  end: number
}

/** Puts one part to a presigned URL and returns the storage ETag. */
export type PutPart = (
  url: string,
  body: Blob,
  onProgress: (loadedBytes: number) => void,
  signal: AbortSignal,
) => Promise<string>

export interface UploadOptions {
  scenario: Scenario
  contentType: string
  putPart: PutPart
  signal: AbortSignal
  concurrency?: number
  onRegistered?: (recording: Recording, plan: UploadPlan) => void
  onStage?: (stage: Stage) => void
  onProgress?: (uploadedBytes: number, totalBytes: number) => void
}

const CORRUPTED_ETAG = '"00000000000000000000000000000000"'

const EXTENSION_TYPES: Record<string, string> = {
  aac: 'audio/aac',
  flac: 'audio/flac',
  m4a: 'audio/mp4',
  mp3: 'audio/mpeg',
  ogg: 'audio/ogg',
  wav: 'audio/wav',
  webm: 'audio/webm',
}

export function guessContentType(file: File): string {
  if (file.type) return file.type
  const extension = file.name.split('.').pop()?.toLowerCase() ?? ''
  return EXTENSION_TYPES[extension] ?? 'application/octet-stream'
}

export function planParts(fileSize: number, plan: UploadPlan): PartRange[] {
  return Array.from({ length: plan.part_count }, (_, index) => ({
    partNumber: index + 1,
    start: Math.min(index * plan.part_size_bytes, fileSize),
    end: Math.min((index + 1) * plan.part_size_bytes, fileSize),
  }))
}

export async function uploadFile(api: Api, file: File, options: UploadOptions): Promise<Recording> {
  const { scenario, signal } = options
  options.onStage?.('registering')
  const { recording, upload } = await api.register({
    filename: file.name,
    content_type: options.contentType,
    size_bytes: scenario === 'wrong-size' ? file.size + 1 : file.size,
  })
  options.onRegistered?.(recording, upload)

  const stopParts = new AbortController()
  const stop = () => stopParts.abort()
  signal.addEventListener('abort', stop)
  try {
    if (signal.aborted) throw new DOMException('Upload cancelled', 'AbortError')
    options.onStage?.('uploading')
    const parts = await uploadParts(api, file, recording.id, upload, options, stopParts.signal)
    if (parts === 'abort-requested') {
      options.onStage?.('aborting')
      return await api.abort(recording.id)
    }
    if (scenario === 'wrong-etag') parts[0] = { ...parts[0], etag: CORRUPTED_ETAG }

    options.onStage?.('completing')
    return await api.complete(recording.id, parts)
  } catch (error) {
    if (signal.aborted) {
      await api.abort(recording.id).catch(() => undefined)
    }
    throw error
  } finally {
    signal.removeEventListener('abort', stop)
    options.onStage?.('done')
  }
}

async function uploadParts(
  api: Api,
  file: File,
  recordingId: string,
  plan: UploadPlan,
  options: UploadOptions,
  signal: AbortSignal,
): Promise<CompletedPart[] | 'abort-requested'> {
  const queue = planParts(file.size, plan)
  const loaded = new Map<number, number>()
  const completed: CompletedPart[] = []
  let abortRequested = false

  const report = () => {
    let total = 0
    for (const bytes of loaded.values()) total += bytes
    options.onProgress?.(total, file.size)
  }

  const worker = async () => {
    for (let part = queue.shift(); part; part = queue.shift()) {
      if (signal.aborted || abortRequested) return
      const { url } =
        part.partNumber === 1
          ? plan.first_part
          : await api.partUploadUrl(recordingId, part.partNumber)
      const partNumber = part.partNumber
      const etag = await options.putPart(
        url,
        file.slice(part.start, part.end),
        (bytes) => {
          loaded.set(partNumber, bytes)
          report()
        },
        signal,
      )
      loaded.set(partNumber, part.end - part.start)
      report()
      completed.push({ part_number: partNumber, etag })
      if (options.scenario === 'abort-midway') abortRequested = true
    }
  }

  const workers = Math.max(1, Math.min(options.concurrency ?? 3, plan.part_count))
  await Promise.all(Array.from({ length: workers }, worker))
  if (signal.aborted) throw new DOMException('Upload cancelled', 'AbortError')
  if (abortRequested) return 'abort-requested'
  return completed.sort((a, b) => a.part_number - b.part_number)
}

export const xhrPutPart: PutPart = (url, body, onProgress, signal) =>
  new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('PUT', url)
    xhr.upload.onprogress = (event) => onProgress(event.loaded)
    xhr.onload = () => {
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(`Storage rejected part: HTTP ${xhr.status}`))
        return
      }
      const etag = xhr.getResponseHeader('ETag')
      if (etag) resolve(etag)
      else reject(new Error('No ETag in storage response: bucket CORS must expose ETag'))
    }
    xhr.onerror = () => reject(new Error('Network error uploading to storage (check bucket CORS)'))
    xhr.onabort = () => reject(new DOMException('Upload cancelled', 'AbortError'))
    signal.addEventListener('abort', () => xhr.abort(), { once: true })
    xhr.send(body)
  })
