import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, type Api, type Processing, type Recording } from './api'
import { guessContentType, uploadFile, xhrPutPart } from './upload'

export function useRecordings(api: Api) {
  const [items, setItems] = useState<Recording[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<unknown>(null)
  const [reloads, setReloads] = useState(0)

  useEffect(() => {
    let ignore = false
    api
      .list(null)
      .then((page) => {
        if (ignore) return
        setError(null)
        setItems(page.items)
        setCursor(page.next_cursor)
      })
      .catch((err: unknown) => !ignore && setError(err))
      .finally(() => !ignore && setLoading(false))
    return () => {
      ignore = true
    }
  }, [api, reloads])

  const reload = useCallback(() => setReloads((n) => n + 1), [])

  const loadMore = async () => {
    if (!cursor) return
    const page = await api.list(cursor)
    setItems((current) => [...current, ...page.items])
    setCursor(page.next_cursor)
  }

  return { items, loading, error, hasMore: cursor !== null, reload, loadMore }
}

const POLL_MS = 2000
// Jobs appear within seconds of an upload; past this, the recording was never queued.
const GIVE_UP_AFTER_MS = 2 * 60 * 1000

export interface ProcessingState {
  processing: Processing | null
  notProcessed: boolean
}

/** Polls while a job may still change: not created yet (404) or running. */
export function useProcessing(api: Api, recording: Recording | null): ProcessingState {
  // Keyed by recording, so a previous recording's data is never shown for a new one.
  const [state, setState] = useState<{ id: string } & ProcessingState>()
  const recordingId = recording?.status === 'uploaded' ? recording.id : null
  const uploadedAt = recording?.uploaded_at ?? null

  useEffect(() => {
    if (!recordingId) return
    let ignore = false
    let timer: ReturnType<typeof setTimeout> | undefined

    const poll = async () => {
      let next: Processing | null = null
      try {
        next = await api.processing(recordingId)
      } catch (err) {
        if (!(err instanceof ApiError && err.status === 404)) console.warn(err)
      }
      if (ignore) return
      const waitedTooLong =
        next === null && uploadedAt !== null && Date.now() - Date.parse(uploadedAt) > GIVE_UP_AFTER_MS
      setState({ id: recordingId, processing: next, notProcessed: waitedTooLong })
      if (!waitedTooLong && (next === null || next.status === 'running')) {
        timer = setTimeout(poll, POLL_MS)
      }
    }
    void poll()
    return () => {
      ignore = true
      clearTimeout(timer)
    }
  }, [api, recordingId, uploadedAt])

  if (!state || state.id !== recordingId) return { processing: null, notProcessed: false }
  return { processing: state.processing, notProcessed: state.notProcessed }
}

export interface UploadProgress {
  key: string
  filename: string
  size: number
  progress: number
}

export function useUploads(
  api: Api,
  onUploaded: (recording: Recording) => void,
  notify: (message: string, tone?: 'ok' | 'error') => void,
) {
  const [uploads, setUploads] = useState<UploadProgress[]>([])
  const callbacks = useRef({ onUploaded, notify })
  useEffect(() => {
    callbacks.current = { onUploaded, notify }
  })

  const start = useCallback(
    (files: Iterable<File>) => {
      for (const file of files) {
        const key = crypto.randomUUID()
        setUploads((current) => [{ key, filename: file.name, size: file.size, progress: 0 }, ...current])
        const update = (progress: number) =>
          setUploads((current) => current.map((u) => (u.key === key ? { ...u, progress } : u)))

        uploadFile(api, file, {
          scenario: 'normal',
          contentType: guessContentType(file),
          putPart: xhrPutPart,
          signal: new AbortController().signal,
          onProgress: (loaded, total) => update(total ? loaded / total : 1),
        })
          .then((recording) => {
            callbacks.current.onUploaded(recording)
            callbacks.current.notify(
              recording.status === 'uploaded'
                ? `${file.name} uploaded · processing started`
                : `${file.name}: ${recording.failure_reason ?? recording.status}`,
              recording.status === 'uploaded' ? 'ok' : 'error',
            )
          })
          .catch((err: unknown) =>
            callbacks.current.notify(
              `${file.name}: ${err instanceof Error ? err.message : String(err)}`,
              'error',
            ),
          )
          .finally(() => setUploads((current) => current.filter((u) => u.key !== key)))
      }
    },
    [api],
  )

  return { uploads, start }
}
