import { Archive, Plus, RefreshCw, RotateCcw, Search, Trash2 } from 'lucide-react'
import type { GraphSession } from './types'
import type { PlatformHomeSessionListFilter } from './usePlatformHomeGraphSessionList'

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

function isSoftDeletedSession(session: GraphSession): boolean {
  return Boolean(session.metadata?.deleted_at)
}

export default function PlatformHomeLeftSessionLogPane({
  sessions,
  activeSessionId,
  loading,
  error,
  filter,
  setFilter,
  searchText,
  setSearchText,
  onRefresh,
  onNewSession,
  onSelectSession,
  onArchiveSession,
  onRestoreSession,
  onSoftDeleteSession,
}: {
  sessions: GraphSession[]
  activeSessionId?: string
  loading: boolean
  error: string
  filter: PlatformHomeSessionListFilter
  setFilter: (filter: PlatformHomeSessionListFilter) => void
  searchText: string
  setSearchText: (value: string) => void
  onRefresh: () => void
  onNewSession: () => void
  onSelectSession: (sessionId: string) => void
  onArchiveSession: (session: GraphSession) => void
  onRestoreSession: (session: GraphSession) => void
  onSoftDeleteSession: (session: GraphSession) => void
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
        <div className="platform-session-search">
          <Search size={13} />
          <input value={searchText} onChange={event => setSearchText(event.target.value)} placeholder="Search sessions..." />
        </div>
        <div className="platform-filter-row">
          {(['active', 'archived', 'trash', 'all'] as PlatformHomeSessionListFilter[]).map(nextFilter => (
            <button key={nextFilter} className={filter === nextFilter ? 'active' : ''} onClick={() => setFilter(nextFilter)}>{nextFilter}</button>
          ))}
        </div>
        {error && <div className="home-error">{error}</div>}
        {loading && <p className="platform-muted-text">Loading sessions…</p>}
        {!loading && sessions.length === 0 && <p className="platform-muted-text">No graph sessions in this filter.</p>}
        {sessions.map(session => (
          <div key={session.id} className={`platform-session-row-wrap ${activeSessionId === session.id ? 'active' : ''}`}>
            <button className="platform-session-row" onClick={() => onSelectSession(session.id)}>
              <span className="platform-session-row-title">{session.title || session.id}</span>
              <span className="platform-session-row-meta">
                <span>{session.kind}</span>
                <span>{isSoftDeletedSession(session) ? 'trash' : session.status || 'unknown'}</span>
                <span>{shortRelativeTime(session.updated_at || session.created_at)}</span>
              </span>
            </button>
            <div className="platform-session-row-actions">
              {(session.status === 'archived' || isSoftDeletedSession(session)) ? (
                <button onClick={() => onRestoreSession(session)} title="Restore"><RotateCcw size={12} /></button>
              ) : (
                <button onClick={() => onArchiveSession(session)} title="Archive"><Archive size={12} /></button>
              )}
              {!isSoftDeletedSession(session) && <button onClick={() => onSoftDeleteSession(session)} title="Move to trash"><Trash2 size={12} /></button>}
            </div>
          </div>
        ))}
      </div>
    </aside>
  )
}
