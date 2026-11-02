import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import type { Api, Processing, Recording } from '../api'
import { STATUS_LABELS, activeSegmentIndex, formatLabel } from '../derive'
import { formatDateTime, formatDuration, splitBytes } from '../format'
import { AudioPreview, type Player } from './AudioPreview'
import { ClockIcon, CopyIcon, DriveIcon, FileAudioIcon, PlusIcon, SpeechIcon } from './Icons'
import { Transcript } from './Transcript'

export function Overview({
  api,
  recording,
  processing,
  waiting,
  onUpload,
  notify,
}: {
  api: Api
  recording: Recording | null
  processing: Processing | null
  waiting: boolean
  onUpload: () => void
  notify: (message: string) => void
}) {
  if (!recording) {
    return (
      <div className="card empty">
        <h2>No recordings yet</h2>
        <p className="muted">Upload audio to see its waveform and detected speech.</p>
        <button type="button" className="button button--primary" onClick={onUpload}>
          <PlusIcon /> Upload audio
        </button>
      </div>
    )
  }
  return (
    <SelectedRecording
      key={recording.id}
      api={api}
      recording={recording}
      processing={processing}
      waiting={waiting}
      notify={notify}
    />
  )
}

function SelectedRecording({
  api,
  recording,
  processing,
  waiting,
  notify,
}: {
  api: Api
  recording: Recording
  processing: Processing | null
  waiting: boolean
  notify: (message: string) => void
}) {
  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const [positionMs, setPositionMs] = useState(0)
  // Wordless segments (breaths, grunts, music VAD let through) stay out of sight on
  // the waveform and in the transcript until asked for.
  const [showSilent, setShowSilent] = useState(false)
  const toggleSilent = useCallback(() => setShowSilent((show) => !show), [])
  const player = useRef<Player | null>(null)
  const uploaded = recording.status === 'uploaded'
  const onTime = useCallback((seconds: number) => setPositionMs(seconds * 1000), [])
  const seek = useCallback((seconds: number) => player.current?.playFrom(seconds), [])

  useEffect(() => {
    if (!uploaded) return
    let ignore = false
    api
      .downloadUrl(recording.id)
      .then(({ url }) => !ignore && setAudioUrl(url))
      .catch(() => undefined)
    return () => {
      ignore = true
    }
  }, [api, recording.id, uploaded])

  const vad = processing?.vad ?? null
  // Once transcribed, both the waveform and the transcript show the segments the two
  // stages agree on: whole VAD segments holding whole sentences.
  const lines = processing?.transcription?.segments
  const highlighted = lines ?? vad?.segments ?? null
  const activeIndex = lines ? activeSegmentIndex(lines, positionMs) : -1
  const [size, sizeUnit] = splitBytes(recording.size_bytes)
  const pending = waiting ? '…' : '—'

  return (
    <>
      <header className="selected">
        <div>
          <h1>{recording.filename}</h1>
          <div className="selected__meta muted">
            {formatDateTime(recording.created_at)}
            {!uploaded && (
              <span className={`badge badge--${recording.status}`}>
                {STATUS_LABELS[recording.status]}
              </span>
            )}
          </div>
        </div>
        <button
          type="button"
          className="button button--small"
          onClick={() =>
            void navigator.clipboard.writeText(recording.id).then(() => notify('Recording ID copied'))
          }
        >
          <CopyIcon width={14} height={14} /> Copy ID
        </button>
      </header>

      <AudioPreview
        url={uploaded ? audioUrl : null}
        segments={highlighted}
        hideSilent={!showSilent}
        activeIndex={activeIndex}
        placeholder={
          recording.status === 'pending_upload'
            ? 'The waveform appears once the upload completes.'
            : 'This recording was not stored.'
        }
        ref={player}
        onTime={onTime}
      />

      <div className="stats">
        <Stat
          label="Duration"
          icon={<ClockIcon />}
          value={vad ? formatDuration(vad.duration_ms / 1000) : pending}
        />
        <Stat label="Size" icon={<DriveIcon />} value={size} unit={sizeUnit} />
        <Stat label="Format" icon={<FileAudioIcon />} value={formatLabel(recording.content_type)} />
        <Stat
          label="Speech"
          icon={<SpeechIcon />}
          value={vad ? `${Math.round(vad.speech_ratio * 100)}` : pending}
          unit={vad ? '%' : undefined}
        />
      </div>

      <Transcript
        processing={processing}
        activeIndex={activeIndex}
        showSilent={showSilent}
        onToggleSilent={toggleSilent}
        onSeek={seek}
        notify={notify}
      />
    </>
  )
}

function Stat({
  label,
  icon,
  value,
  unit,
}: {
  label: string
  icon: ReactNode
  value: string
  unit?: string
}) {
  return (
    <div className="card stat">
      <div className="stat__head">
        <span>{label}</span>
        <span className="muted">{icon}</span>
      </div>
      <div className="stat__value">
        {value}
        {unit && <small>{unit}</small>}
      </div>
    </div>
  )
}
