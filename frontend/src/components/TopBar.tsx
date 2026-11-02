import { useEffect, useState } from 'react'
import { fetchHealth, type Health } from '../api'
import { PlusIcon } from './Icons'

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function useHealthy(): boolean | null {
  const [healthy, setHealthy] = useState<boolean | null>(null)
  useEffect(() => {
    let cancelled = false
    const poll = () =>
      fetchHealth()
        .then((health: Health) => !cancelled && setHealthy(health.status !== 'fail'))
        .catch(() => !cancelled && setHealthy(false))
    void poll()
    const timer = setInterval(poll, 15_000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])
  return healthy
}

export function TopBar({
  userId,
  onSwitchUser,
  onUpload,
}: {
  userId: string
  onSwitchUser: (id: string) => void
  onUpload: () => void
}) {
  const healthy = useHealthy()
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState(userId)

  return (
    <header className="topbar">
      <span
        className={`env${healthy === false ? ' env--down' : ''}`}
        title={healthy === false ? 'API is not ready' : 'API is ready'}
      >
        <span className="dot" /> {healthy === false ? 'API unavailable' : 'Development'}
      </span>
      <div className="topbar__right">
        <button type="button" className="button button--primary" onClick={onUpload}>
          <PlusIcon /> Upload audio
        </button>
        <div className="user">
          <button
            type="button"
            className="avatar"
            onClick={() => {
              setDraft(userId)
              setOpen((value) => !value)
            }}
            aria-label="Development user"
          >
            {userId.slice(0, 2).toUpperCase()}
          </button>
          {open && (
            <div className="popover">
              <div className="eyebrow">Development user</div>
              <p className="muted small">Each user sees only their own recordings.</p>
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value.trim())}
                spellCheck={false}
                className={UUID_PATTERN.test(draft) ? '' : 'invalid'}
              />
              <div className="popover__actions">
                <button
                  type="button"
                  className="button"
                  onClick={() => {
                    onSwitchUser(crypto.randomUUID())
                    setOpen(false)
                  }}
                >
                  New user
                </button>
                <button
                  type="button"
                  className="button button--primary"
                  disabled={!UUID_PATTERN.test(draft) || draft === userId}
                  onClick={() => {
                    onSwitchUser(draft)
                    setOpen(false)
                  }}
                >
                  Switch
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
