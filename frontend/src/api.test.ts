import { describe, expect, it } from 'vitest'
import { ApiError, createApi } from './api'

function fetchReturning(status: number, body: unknown, seen: Request[] = []): typeof fetch {
  return async (input, init) => {
    seen.push(new Request(new URL(String(input), 'http://test'), init))
    return new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    })
  }
}

describe('createApi', () => {
  it('sends the dev user header and JSON body', async () => {
    const seen: Request[] = []
    const api = createApi('user-1', fetchReturning(201, { recording: {}, upload: {} }, seen))

    await api.register({ filename: 'a.mp3', content_type: 'audio/mpeg', size_bytes: 1 })

    expect(seen[0].method).toBe('POST')
    expect(new URL(seen[0].url).pathname).toBe('/api/v1/recordings')
    expect(seen[0].headers.get('X-Dev-User-Id')).toBe('user-1')
    expect(await seen[0].json()).toEqual({
      filename: 'a.mp3',
      content_type: 'audio/mpeg',
      size_bytes: 1,
    })
  })

  it('turns the error envelope into an ApiError', async () => {
    const api = createApi(
      'user-1',
      fetchReturning(409, {
        error: { code: 'conflict', message: 'recording is aborted', request_id: 'req-9' },
      }),
    )

    const error = await api.get('rec-1').catch((e: unknown) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      status: 409,
      code: 'conflict',
      message: 'recording is aborted',
      requestId: 'req-9',
    })
  })
})
