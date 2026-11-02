import { ApiError } from '../api'

export function ErrorMessage({ error }: { error: unknown }) {
  if (error instanceof ApiError) {
    return (
      <p className="error-text">
        {error.status} <code>{error.code}</code>: {error.message}
        {error.requestId && <span className="muted"> (request {error.requestId})</span>}
      </p>
    )
  }
  return <p className="error-text">{error instanceof Error ? error.message : String(error)}</p>
}
