import { memo, useEffect, useRef } from 'react'
import type { Processing } from '../api'
import { formatDuration, languageName } from '../format'
import { CopyIcon } from './Icons'

/** The transcript of the selected recording; lines seek the player to their start. */
export const Transcript = memo(function Transcript({
  processing,
  activeIndex,
  showSilent,
  onToggleSilent,
  onSeek,
  notify,
}: {
  processing: Processing | null
  activeIndex: number
  /** Show segments VAD found but Whisper heard no words in (breaths, grunts, music). */
  showSilent: boolean
  onToggleSilent: () => void
  onSeek: (seconds: number) => void
  notify: (message: string) => void
}) {
  const list = useRef<HTMLOListElement>(null)

  useEffect(() => {
    // Keep the line being played visible without scrolling the page itself.
    const box = list.current
    const line = activeIndex >= 0 ? box?.querySelector(`[data-index="${activeIndex}"]`) : null
    if (!box || !(line instanceof HTMLElement)) return
    const top = line.offsetTop - box.offsetTop
    if (top < box.scrollTop || top + line.offsetHeight > box.scrollTop + box.clientHeight) {
      box.scrollTo({ top: top - box.clientHeight / 3, behavior: 'smooth' })
    }
  }, [activeIndex, showSilent])

  if (!processing || processing.speech_detected === false) return null
  const asr = processing.stages.find((stage) => stage.name === 'asr')
  const transcription = processing.transcription

  if (!transcription) {
    if (processing.status === 'failed' && asr?.status === 'failed') {
      return (
        <section className="card transcript">
          <span className="eyebrow eyebrow--dot">Transcript</span>
          <p className="error-text small transcript__status">{asr.error ?? 'Transcription failed'}</p>
        </section>
      )
    }
    if (processing.status !== 'running' || !processing.speech_detected) return null
    return (
      <section className="card transcript">
        <span className="eyebrow eyebrow--dot">Transcript</span>
        <p className="muted small transcript__status">Transcribing speech…</p>
      </section>
    )
  }

  const confidence = Math.round(transcription.language_probability * 100)
  const silent = transcription.segments.filter((segment) => !segment.text).length
  const shown = transcription.segments
    .map((segment, index) => ({ segment, index }))
    .filter(({ segment }) => showSilent || segment.text)
  return (
    <section className="card transcript">
      <header className="transcript__header">
        <span className="eyebrow eyebrow--dot">Transcript</span>
        <div className="transcript__actions">
          <span className="chip" title={`Language detected with ${confidence}% confidence`}>
            {languageName(transcription.language)} · {confidence}%
          </span>
          <button
            type="button"
            className="button button--small"
            disabled={!transcription.text}
            onClick={() =>
              void navigator.clipboard
                .writeText(transcription.text)
                .then(() => notify('Transcript copied'))
            }
          >
            <CopyIcon width={14} height={14} /> Copy text
          </button>
        </div>
      </header>
      {shown.length ? (
        <ol ref={list} className="transcript__lines">
          {shown.map(({ segment, index }) => (
            <li key={index} data-index={index}>
              <button
                type="button"
                className={`transcript__line${index === activeIndex ? ' transcript__line--active' : ''}`}
                onClick={() => onSeek(segment.start_ms / 1000)}
              >
                <span className="transcript__time">{formatDuration(segment.start_ms / 1000)}</span>
                {segment.text ? (
                  <span>{segment.text}</span>
                ) : (
                  <span className="muted">No words recognized</span>
                )}
              </button>
            </li>
          ))}
        </ol>
      ) : (
        <p className="muted small transcript__status">No words were recognized in the speech.</p>
      )}
      {silent > 0 && (
        <button type="button" className="link-button" onClick={onToggleSilent}>
          {showSilent
            ? 'Hide segments without words'
            : `Show ${silent} segment${silent === 1 ? '' : 's'} without words`}
        </button>
      )}
    </section>
  )
})
