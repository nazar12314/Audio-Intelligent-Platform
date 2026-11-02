/** Waveform zoom, in pixels per second of audio. */

// Long recordings open showing this much audio, so segments are wide enough to read.
export const DEFAULT_VIEW_S = 60
// About word level: a 200 ms word gets 80 px.
export const MAX_PX_PER_SEC = 400

/** The zoom that shows the whole recording in `width` pixels. */
export function fitZoom(width: number, duration: number): number {
  return duration > 0 ? width / duration : 0
}

export function initialZoom(width: number, duration: number): number {
  return duration > DEFAULT_VIEW_S ? width / DEFAULT_VIEW_S : fitZoom(width, duration)
}

export function clampZoom(pxPerSec: number, width: number, duration: number): number {
  const fit = fitZoom(width, duration)
  return Math.min(Math.max(pxPerSec, fit), Math.max(MAX_PX_PER_SEC, fit))
}

/** Seconds of audio visible at a zoom. */
export function visibleSeconds(pxPerSec: number, width: number, duration: number): number {
  return pxPerSec > 0 ? Math.min(width / pxPerSec, duration) : duration
}
