import { describe, expect, it } from 'vitest'
import { clampZoom, fitZoom, initialZoom, visibleSeconds } from './zoom'

const WIDTH = 900

describe('waveform zoom', () => {
  it('opens long recordings on a one-minute view and short ones whole', () => {
    expect(visibleSeconds(initialZoom(WIDTH, 780), WIDTH, 780)).toBe(60)
    expect(initialZoom(WIDTH, 30)).toBe(fitZoom(WIDTH, 30))
    expect(visibleSeconds(initialZoom(WIDTH, 30), WIDTH, 30)).toBe(30)
  })

  it('never zooms out past the whole recording or in past word level', () => {
    expect(clampZoom(0.1, WIDTH, 780)).toBe(fitZoom(WIDTH, 780))
    expect(clampZoom(10_000, WIDTH, 780)).toBe(400)
    expect(clampZoom(50, WIDTH, 780)).toBe(50)
  })

  it('lets a recording too short to fill the view stay whole', () => {
    expect(clampZoom(400, WIDTH, 1)).toBe(900)
  })
})
