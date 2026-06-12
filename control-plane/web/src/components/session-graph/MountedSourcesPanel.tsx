import { ArrowRight, GitBranch, Info, Unplug } from 'lucide-react'
import type { SessionEdgeView, SessionView } from './sessionGraphTypes'
import { formatId, sessionTitle } from './sessionGraphTypes'

function sessionKindById(sessions: Map<string, SessionView>, sessionId: string): string {
  return sessions.get(sessionId)?.kind || 'session'
}

function edgeLabel(edge: SessionEdgeView): string {
  if (edge.type === 'mounted_under') return 'mounted under'
  if (edge.type === 'adapted_under') return 'adapted under'
  if (edge.type === 'component_of') return 'component of'
  return edge.type.replace(/_/g, ' ')
}

export default function MountedSourcesPanel({
  sessions,
  edges,
  selectedEdgeId,
  onSelectEdge,
  onUnmount,
  busy,
}: {
  sessions: SessionView[]
  edges: SessionEdgeView[]
  selectedEdgeId?: string
  onSelectEdge?: (edgeId: string) => void
  onUnmount?: (edge: SessionEdgeView) => void
  busy?: boolean
}) {
  const mountedEdges = edges.filter(edge => edge.type === 'mounted_under' || edge.type === 'component_of' || edge.type === 'adapted_under')
  const sessionById = new Map(sessions.map(session => [session.id, session]))
  const targetCount = new Set(mountedEdges.map(edge => edge.target_session_id)).size

  return (
    <section className="sg-card">
      <div className="sg-card-header sg-card-header-split">
        <div>
          <GitBranch size={16} />
          <h3>Mounted sources</h3>
        </div>
        <span className="sg-count-pill">{mountedEdges.length}</span>
      </div>

      <p className="sg-muted sg-small">
        Mounted sources are reusable session context projected into an active session. Repo sessions should usually appear here before runtime execution starts.
      </p>

      {mountedEdges.length > 0 && (
        <div className="sg-tags">
          <span>{targetCount} target sessions</span>
          <span>{mountedEdges.filter(edge => edge.type === 'adapted_under').length} adapted</span>
          <span>{mountedEdges.filter(edge => edge.type === 'mounted_under').length} direct mounts</span>
        </div>
      )}

      {mountedEdges.length === 0 ? (
        <div className="sg-empty-state">
          <Info size={16} />
          <div>
            <strong>No sources mounted yet.</strong>
            <p className="sg-muted sg-small">Create or select a repo session, choose the goal/work session as target, then preview the mount before applying it.</p>
          </div>
        </div>
      ) : (
        <div className="sg-edge-list">
          {mountedEdges.map(edge => {
            const selected = edge.id === selectedEdgeId
            const sourceKind = sessionKindById(sessionById, edge.source_session_id)
            const targetKind = sessionKindById(sessionById, edge.target_session_id)
            return (
              <article key={edge.id} className={`sg-edge-row ${selected ? 'is-selected' : ''}`} onClick={() => onSelectEdge?.(edge.id)}>
                <div className="sg-edge-node">
                  <span>{sessionTitle(sessionById, edge.source_session_id)}</span>
                  <small>{sourceKind} · {formatId(edge.source_session_id)}</small>
                </div>
                <code>{edgeLabel(edge)}</code>
                <ArrowRight size={13} />
                <div className="sg-edge-node">
                  <span>{sessionTitle(sessionById, edge.target_session_id)}</span>
                  <small>{targetKind} · {formatId(edge.target_session_id)}</small>
                </div>
                {edge.metadata?.mount_mode && <span className="sg-mini-tag">{String(edge.metadata.mount_mode)}</span>}
                {edge.type === 'mounted_under' && onUnmount && (
                  <button
                    className="sg-icon-button"
                    type="button"
                    title="Unmount source from target"
                    disabled={busy}
                    onClick={(event) => {
                      event.stopPropagation()
                      onUnmount(edge)
                    }}
                  >
                    <Unplug size={13} />
                  </button>
                )}
              </article>
            )
          })}
        </div>
      )}
    </section>
  )
}
