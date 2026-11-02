import { useState, type DragEvent } from 'react'
import type { Recording } from '../api'
import { STATUS_LABELS } from '../derive'
import { formatBytes, formatRelative } from '../format'
import type { UploadProgress } from '../hooks'
import { PlusIcon, SearchIcon, UploadIcon, WaveIcon } from './Icons'

export function Sidebar({
  recordings,
  uploads,
  selectedId,
  hasMore,
  onSelect,
  onUpload,
  onFiles,
  onLoadMore,
}: {
  recordings: Recording[]
  uploads: UploadProgress[]
  selectedId: string | null
  hasMore: boolean
  onSelect: (id: string) => void
  onUpload: () => void
  onFiles: (files: FileList) => void
  onLoadMore: () => void
}) {
  const [query, setQuery] = useState('')
  const [dragging, setDragging] = useState(false)
  const visible = recordings.filter((r) => r.filename.toLowerCase().includes(query.toLowerCase()))

  const drop = (event: DragEvent) => {
    event.preventDefault()
    setDragging(false)
    if (event.dataTransfer.files.length) onFiles(event.dataTransfer.files)
  }

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand__mark">
          <WaveIcon width={20} height={20} />
        </div>
        <div className="brand__name">sonar.</div>
      </div>

      <div className="library">
        <div className="library__head">
          <h2>
            Recordings <span className="muted">{recordings.length}{hasMore ? '+' : ''}</span>
          </h2>
          <button type="button" className="icon-button" onClick={onUpload} aria-label="Upload audio">
            <PlusIcon />
          </button>
        </div>

        <label className="search">
          <SearchIcon className="muted" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search" />
        </label>

        <ul className="files">
          {uploads.map((upload) => (
            <li key={upload.key} className="file file--uploading">
              <div className="file__name">{upload.filename}</div>
              <div className="muted small">Uploading · {Math.round(upload.progress * 100)}%</div>
              <div className="progress">
                <div className="progress__bar" style={{ width: `${upload.progress * 100}%` }} />
              </div>
            </li>
          ))}
          {visible.map((recording) => (
            <li key={recording.id}>
              <button
                type="button"
                className={`file${recording.id === selectedId ? ' file--selected' : ''}`}
                onClick={() => onSelect(recording.id)}
              >
                <div className="file__name">{recording.filename}</div>
                <div className="file__meta">
                  <span className="muted small">
                    {formatRelative(recording.created_at)} · {formatBytes(recording.size_bytes)}
                  </span>
                  {recording.status !== 'uploaded' && (
                    <span className={`badge badge--${recording.status}`}>
                      {STATUS_LABELS[recording.status]}
                    </span>
                  )}
                </div>
              </button>
            </li>
          ))}
          {!visible.length && !uploads.length && (
            <li className="muted small files__empty">
              {recordings.length ? 'No recordings match.' : 'No recordings yet.'}
            </li>
          )}
        </ul>
        {hasMore && (
          <button type="button" className="link-button" onClick={onLoadMore}>
            Load more
          </button>
        )}
      </div>

      <div
        className={`dropzone${dragging ? ' dropzone--active' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={drop}
        onClick={onUpload}
        role="button"
        tabIndex={0}
      >
        <UploadIcon />
        <div>
          <strong>Drop audio here</strong>
          <div className="muted small">or click to browse</div>
        </div>
      </div>
    </aside>
  )
}
