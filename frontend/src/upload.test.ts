import { describe, expect, it } from 'vitest'
import type { Api, CompletedPart, Recording, UploadPlan } from './api'
import { guessContentType, planParts, uploadFile, type PutPart, type Scenario } from './upload'

const PLAN: UploadPlan = {
  part_size_bytes: 4,
  part_count: 3,
  url_ttl_s: 900,
  first_part: { part_number: 1, url: 'https://storage.test/part/1', expires_at: '' },
}

function recording(status: Recording['status'] = 'pending_upload'): Recording {
  return {
    id: 'rec-1',
    filename: 'a.mp3',
    content_type: 'audio/mpeg',
    size_bytes: 10,
    status,
    failure_reason: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    uploaded_at: null,
  }
}

function fakeApi() {
  const calls = {
    register: [] as { size_bytes: number; content_type: string }[],
    partUrlRequests: [] as number[],
    complete: [] as CompletedPart[][],
    abort: 0,
  }
  const api = {
    register: async (body: { filename: string; content_type: string; size_bytes: number }) => {
      calls.register.push(body)
      return { recording: recording(), upload: PLAN }
    },
    partUploadUrl: async (_id: string, n: number) => {
      calls.partUrlRequests.push(n)
      return {
      part_number: n,
        url: `https://storage.test/part/${n}`,
        expires_at: '',
      }
    },
    complete: async (_id: string, parts: CompletedPart[]) => {
      calls.complete.push(parts)
      return recording('uploaded')
    },
    abort: async () => {
      calls.abort += 1
      return recording('aborted')
    },
  } as unknown as Api
  return { api, calls }
}

function recordingPut() {
  const bodies = new Map<string, string>()
  const put: PutPart = async (url, body) => {
    bodies.set(url, await body.text())
    return `"etag-${url.split('/').pop()}"`
  }
  return { put, bodies }
}

const file = new File(['0123456789'], 'a.mp3', { type: 'audio/mpeg' })

async function run(scenario: Scenario, signal = new AbortController().signal) {
  const { api, calls } = fakeApi()
  const { put, bodies } = recordingPut()
  const result = await uploadFile(api, file, {
    scenario,
    contentType: 'audio/mpeg',
    putPart: put,
    signal,
    concurrency: 1,
  })
  return { result, calls, bodies }
}

describe('planParts', () => {
  it('splits the file into full parts and a remainder', () => {
    expect(planParts(10, PLAN)).toEqual([
      { partNumber: 1, start: 0, end: 4 },
      { partNumber: 2, start: 4, end: 8 },
      { partNumber: 3, start: 8, end: 10 },
    ])
  })
})

describe('uploadFile', () => {
  it('uploads every byte range and completes with the ETags in order', async () => {
    const { result, calls, bodies } = await run('normal')

    expect(calls.register[0].size_bytes).toBe(10)
    expect([...bodies.values()]).toEqual(['0123', '4567', '89'])
    expect(calls.complete[0]).toEqual([
      { part_number: 1, etag: '"etag-1"' },
      { part_number: 2, etag: '"etag-2"' },
      { part_number: 3, etag: '"etag-3"' },
    ])
    expect(result.status).toBe('uploaded')
  })

  it('uses the URL from registration for the first part', async () => {
    const { calls } = await run('normal')
    expect(calls.partUrlRequests).toEqual([2, 3])
  })

  it('declares one byte too many for the wrong-size scenario', async () => {
    const { calls } = await run('wrong-size')
    expect(calls.register[0].size_bytes).toBe(11)
  })

  it('corrupts the first ETag for the wrong-etag scenario', async () => {
    const { calls } = await run('wrong-etag')
    expect(calls.complete[0][0].etag).not.toBe('"etag-1"')
    expect(calls.complete[0][1].etag).toBe('"etag-2"')
  })

  it('aborts after the first part for the abort-midway scenario', async () => {
    const { result, calls, bodies } = await run('abort-midway')
    expect(bodies.size).toBe(1)
    expect(calls.abort).toBe(1)
    expect(calls.complete).toHaveLength(0)
    expect(result.status).toBe('aborted')
  })

  it('aborts the recording when the user cancels', async () => {
    const { api, calls } = fakeApi()
    const controller = new AbortController()
    const put: PutPart = async (_url, _body, _progress, signal) => {
      controller.abort()
      throw signal.reason ?? new DOMException('cancelled', 'AbortError')
    }

    await expect(
      uploadFile(api, file, {
        scenario: 'normal',
        contentType: 'audio/mpeg',
        putPart: put,
        signal: controller.signal,
      }),
    ).rejects.toThrow()
    expect(calls.abort).toBe(1)
  })
})

describe('guessContentType', () => {
  it('prefers the browser type, then the extension', () => {
    expect(guessContentType(new File([], 'x.bin', { type: 'audio/ogg' }))).toBe('audio/ogg')
    expect(guessContentType(new File([], 'Voice.M4A'))).toBe('audio/mp4')
    expect(guessContentType(new File([], 'notes.txt'))).toBe('application/octet-stream')
  })
})
