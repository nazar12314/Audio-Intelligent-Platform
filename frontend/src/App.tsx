import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createApi, type Recording } from './api'
import { ErrorMessage } from './components/ErrorMessage'
import { Inspector } from './components/Inspector'
import { Overview } from './components/Overview'
import { Sidebar } from './components/Sidebar'
import { TopBar } from './components/TopBar'
import { useProcessing, useRecordings, useUploads } from './hooks'

const USER_KEY = 'audio-platform:dev-user-id'
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function initialUserId(): string {
  const fromUrl = new URLSearchParams(window.location.search).get('user')
  if (fromUrl && UUID_PATTERN.test(fromUrl)) {
    localStorage.setItem(USER_KEY, fromUrl)
    return fromUrl
  }
  const saved = localStorage.getItem(USER_KEY)
  if (saved && UUID_PATTERN.test(saved)) return saved
  const created = crypto.randomUUID()
  localStorage.setItem(USER_KEY, created)
  return created
}

interface Toast {
  id: number
  message: string
  tone: 'ok' | 'error'
}

export default function App() {
  const [userId, setUserId] = useState(initialUserId)
  const api = useMemo(() => createApi(userId), [userId])
  const { items, error, hasMore, reload, loadMore } = useRecordings(api)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [toast, setToast] = useState<Toast | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  const notify = useCallback((message: string, tone: 'ok' | 'error' = 'ok') => {
    setToast({ id: Date.now(), message, tone })
  }, [])

  const { uploads, start } = useUploads(
    api,
    (recording: Recording) => {
      setSelectedId(recording.id)
      reload()
    },
    notify,
  )

  useEffect(() => {
    if (!toast) return
    const timer = setTimeout(() => setToast(null), 4000)
    return () => clearTimeout(timer)
  }, [toast])

  const selected = items.find((r) => r.id === selectedId) ?? items[0] ?? null
  const { processing, notProcessed } = useProcessing(api, selected)
  const waiting =
    selected?.status === 'uploaded' && !notProcessed && (!processing || processing.status === 'running')

  const switchUser = (id: string) => {
    localStorage.setItem(USER_KEY, id)
    setUserId(id)
    setSelectedId(null)
  }

  return (
    <div className="shell">
      <Sidebar
        recordings={items}
        uploads={uploads}
        selectedId={selected?.id ?? null}
        hasMore={hasMore}
        onSelect={setSelectedId}
        onUpload={() => fileInput.current?.click()}
        onFiles={start}
        onLoadMore={() => void loadMore()}
      />
      <main className="main">
        <TopBar userId={userId} onSwitchUser={switchUser} onUpload={() => fileInput.current?.click()} />
        <div className="main__scroll">
          <div className="content">
            {error !== null && <ErrorMessage error={error} />}
            <Overview
            api={api}
            recording={selected}
            processing={processing}
            waiting={waiting}
            onUpload={() => fileInput.current?.click()}
              notify={notify}
            />
          </div>
        </div>
      </main>
      <Inspector recording={selected} processing={processing} notProcessed={notProcessed} />
      <input
        ref={fileInput}
        type="file"
        accept="audio/*"
        multiple
        hidden
        onChange={(e) => {
          if (e.target.files) start(e.target.files)
          e.target.value = ''
        }}
      />
      {toast && (
        <div key={toast.id} className={`toast toast--${toast.tone}`} role="status">
          {toast.message}
        </div>
      )}
    </div>
  )
}
