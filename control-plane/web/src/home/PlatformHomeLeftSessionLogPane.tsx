import { Archive, Plus, RefreshCw } from 'lucide-react'
import type { GraphSession } from './types'

function shortRelativeTime(iso?: string): string {
  if (!iso) return 'unknown'
  const diff = Date.now() - new Date(iso).getTime()
  const minutes = Math.floor(diff / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

export default function PlatformHomeLeftSessionLogPane({
  sessions,
  activeSessionId,
  loading,
  showArchived,
  onToggleArchived,
  onRefresh,
  onNewSession,
  onSelectSession,
}: {
  sessions: GraphSession[]
  activeSessionId?: string
  loading: boolean
  showArchived: boolean
  onToggleArchived: () => void
  onRefresh: () => void
  onNewSession: () => void
  onSelectSession: (sessionId: string) => void
}) {
  return (
    <aside className="platform-left-pane" aria-label="Session log">
      <div className="platform-pane-header">
        <span className="platform-pane-title">Sessions</span>
        <div>
          <button className="platform-button-plain" onClick={onRefresh} title="Refresh sessions"><RefreshCw size={14} /></button>
          <button className="platform-button-plain" onClick={onNewSession} title="New session"><Plus size={14} /></button>
        </div>
      </div>
      <div className="platform-pane-body">
        <button className="platform-button-plain" onClick={onToggleArchived} style={{ width: '100%', marginBottom: 10 }}>
          <Archive size={14} /> {showArchived ? 'Hide archived' : 'Show archived'}
        </button>
        {loading && <p className="platform-muted-text">Loading sessions…</p>}
        {!loading && sessions.length === 0 && <p className="platform-muted-text">No graph sessions yet.</p>}
        {sessions.map(session => (
          <button key={session.id} className={`platform-session-row ${activeSessionId === session.id ? 'active' : ''}`} onClick={() => onSelectSession(session.id)}>
            <span className="platform-session-row-title">{session.title || session.id}</span>
            <span className="platform-session-row-meta">
              <span>{session.kind}</span>
              <span>{session.status || 'unknown'}</span>
              <span>{shortRelativeTime(session.updated_at || session.created_at)}</span>
            </span>
          </button>
        ))}
      </div>
    </aside>
  )
}
