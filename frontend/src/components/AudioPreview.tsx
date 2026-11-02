import { useEffect, useImperativeHandle, useRef, useState, type Ref } from 'react'
import WaveSurfer from 'wavesurfer.js'
import MinimapPlugin from 'wavesurfer.js/dist/plugins/minimap.esm.js'
import RegionsPlugin, { type Region } from 'wavesurfer.js/dist/plugins/regions.esm.js'
import TimelinePlugin from 'wavesurfer.js/dist/plugins/timeline.esm.js'
import type { SpeechSegment } from '../api'
import { formatDuration } from '../format'
import { DEFAULT_VIEW_S, clampZoom, fitZoom, initialZoom, visibleSeconds } from '../zoom'
import { PauseIcon, PlayIcon, SpeechIcon, VolumeIcon } from './Icons'

const SPEEDS = [1, 1.25, 1.5, 2]
const REGION = 'rgba(159, 240, 216, 0.12)'
const SILENT_REGION = 'rgba(135, 150, 162, 0.08)' // speech without recognized words
const ACTIVE_REGION = 'rgba(159, 240, 216, 0.3)'

function colorOf(segment: { text?: string }): string {
  return segment.text === '' ? SILENT_REGION : REGION
}

/** Lets other components drive playback, e.g. a transcript line seeking to its start. */
export interface Player {
  playFrom(seconds: number): void
}

export function AudioPreview({
  url,
  segments,
  placeholder,
  hideSilent = false,
  activeIndex = -1,
  ref,
  onTime,
}: {
  url: string | null
  segments: (SpeechSegment & { text?: string })[] | null
  placeholder: string
  /** Leave out segments without recognized words (`text === ''`). */
  hideSilent?: boolean
  activeIndex?: number
  ref?: Ref<Player>
  onTime?: (seconds: number) => void
}) {
  const container = useRef<HTMLDivElement>(null)
  const overview = useRef<HTMLDivElement>(null)
  const onTimeRef = useRef(onTime)
  useEffect(() => {
    onTimeRef.current = onTime
  })
  const wavesurfer = useRef<WaveSurfer | null>(null)
  const regions = useRef<ReturnType<typeof RegionsPlugin.create> | null>(null)
  const drawn = useRef<(Region | null)[]>([]) // by segment index; null when hidden
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [duration, setDuration] = useState(0)
  const [position, setPosition] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [volume, setVolume] = useState(0.8)
  const [speed, setSpeed] = useState(1)
  const [zoom, setZoom] = useState(0) // pixels per second; 0 until the audio is ready
  const [width, setWidth] = useState(0)

  useEffect(() => {
    const element = container.current
    if (!url || !element || !overview.current) return
    const plugin = RegionsPlugin.create()
    const ws = WaveSurfer.create({
      container: element,
      height: 128,
      waveColor: '#4fa596',
      progressColor: '#9ff0d8',
      cursorColor: '#9ff0d8',
      barWidth: 3,
      barGap: 2,
      barRadius: 3,
      normalize: true,
      // Zoomed in, the waveform scrolls and keeps the cursor in view while playing.
      autoScroll: true,
      autoCenter: true,
      plugins: [
        plugin,
        TimelinePlugin.create({
          height: 20,
          formatTimeCallback: formatDuration,
          style: { fontSize: '11px', color: '#8796a2' },
        }),
        MinimapPlugin.create({
          container: overview.current,
          height: 28,
          waveColor: '#2d4a52',
          progressColor: '#4fa596',
          cursorColor: '#9ff0d8',
          overlayColor: 'rgba(159, 240, 216, 0.14)',
          normalize: true,
        }),
      ],
    })
    wavesurfer.current = ws
    regions.current = plugin
    ws.on('ready', (seconds) => {
      setDuration(seconds)
      setZoom(initialZoom(element.clientWidth, seconds))
      setState('ready')
    })

    // ⌘/Ctrl + wheel (and trackpad pinch, which arrives as one) zooms; plain wheel
    // and swipes keep scrolling.
    const onWheel = (event: WheelEvent) => {
      if (!(event.ctrlKey || event.metaKey) || !ws.getDuration()) return
      event.preventDefault()
      const factor = Math.exp(-event.deltaY / 200)
      setZoom((z) => clampZoom(z * factor, element.clientWidth, ws.getDuration()))
    }
    element.addEventListener('wheel', onWheel, { passive: false })
    const resized = new ResizeObserver(() => setWidth(element.clientWidth))
    resized.observe(element)
    ws.on('timeupdate', (seconds) => {
      setPosition(seconds)
      onTimeRef.current?.(seconds)
    })
    ws.on('play', () => setPlaying(true))
    ws.on('pause', () => setPlaying(false))
    ws.on('finish', () => setPlaying(false))
    ws.on('error', () => setState('error'))
    ws.load(url).catch(() => undefined) // failures arrive through the 'error' event
    return () => {
      element.removeEventListener('wheel', onWheel)
      resized.disconnect()
      ws.destroy()
      wavesurfer.current = null
      regions.current = null
    }
  }, [url])

  useImperativeHandle(
    ref,
    () => ({
      playFrom: (seconds) => {
        const ws = wavesurfer.current
        if (!ws) return
        ws.setTime(seconds)
        void ws.play()
      },
    }),
    [],
  )

  useEffect(() => {
    const plugin = regions.current
    if (!plugin || state !== 'ready') return
    plugin.clearRegions()
    drawn.current = (segments ?? []).map((segment) =>
      hideSilent && segment.text === ''
        ? null
        : plugin.addRegion({
            start: segment.start_ms / 1000,
            end: segment.end_ms / 1000,
            color: colorOf(segment),
            drag: false,
            resize: false,
          }),
    )
  }, [segments, hideSilent, state])

  useEffect(() => {
    const region = drawn.current[activeIndex]
    const segment = segments?.[activeIndex]
    if (!region || !segment) return
    region.setOptions({ color: ACTIVE_REGION })
    return () => region.setOptions({ color: colorOf(segment) })
  }, [activeIndex, segments, hideSilent, state])

  useEffect(() => {
    if (state === 'ready' && zoom > 0) wavesurfer.current?.zoom(zoom)
  }, [zoom, state])

  useEffect(() => wavesurfer.current?.setVolume(volume), [volume])
  useEffect(() => wavesurfer.current?.setPlaybackRate(speed), [speed])

  const changeZoom = (pxPerSec: number) => setZoom(clampZoom(pxPerSec, width, duration))
  const fit = fitZoom(width, duration)
  const visible = visibleSeconds(zoom, width, duration)

  return (
    <section className="card preview">
      <header className="preview__header">
        <span className="eyebrow eyebrow--dot">Audio preview</span>
        <div className="preview__tools">
          {segments && (
            <span className="muted small preview__legend">
              <SpeechIcon width={14} height={14} />
              {segments.length ? 'Speech segments highlighted' : 'No speech detected'}
            </span>
          )}
          {url && state === 'ready' && (
            <div className="zoom" role="group" aria-label="Zoom">
              <button
                type="button"
                className="chip"
                disabled={zoom <= fit}
                onClick={() => changeZoom(zoom / 2)}
                aria-label="Zoom out"
              >
                −
              </button>
              <span className="zoom__view small muted" title="Audio visible at once">
                {formatDuration(visible)}
              </span>
              <button
                type="button"
                className="chip"
                disabled={zoom >= clampZoom(Infinity, width, duration)}
                onClick={() => changeZoom(zoom * 2)}
                aria-label="Zoom in"
              >
                +
              </button>
              <button
                type="button"
                className="chip"
                disabled={zoom <= fit}
                onClick={() => changeZoom(fit)}
              >
                Fit
              </button>
            </div>
          )}
        </div>
      </header>

      {url ? (
        <>
          <div ref={container} className="preview__wave" />
          {state === 'loading' && <p className="muted small">Decoding audio…</p>}
          {state === 'error' && <p className="error-text small">This audio could not be decoded.</p>}
          {/* The whole recording, with the visible part marked; drag it to move. */}
          <div
            ref={overview}
            className="preview__overview"
            hidden={state !== 'ready' || duration <= DEFAULT_VIEW_S}
          />
          <footer className="preview__controls">
            <button
              type="button"
              className="play"
              disabled={state !== 'ready'}
              onClick={() => void wavesurfer.current?.playPause()}
              aria-label={playing ? 'Pause' : 'Play'}
            >
              {playing ? <PauseIcon /> : <PlayIcon />}
            </button>
            <div className="preview__time">
              <strong>{formatDuration(position)}</strong> / {formatDuration(duration)}
            </div>
            <VolumeIcon className="muted" />
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={volume}
              onChange={(e) => setVolume(Number(e.target.value))}
              aria-label="Volume"
            />
            <button
              type="button"
              className="chip"
              onClick={() => setSpeed(SPEEDS[(SPEEDS.indexOf(speed) + 1) % SPEEDS.length])}
              aria-label="Playback speed"
            >
              {speed}×
            </button>
          </footer>
        </>
      ) : (
        <div className="preview__empty muted">{placeholder}</div>
      )}
    </section>
  )
}
