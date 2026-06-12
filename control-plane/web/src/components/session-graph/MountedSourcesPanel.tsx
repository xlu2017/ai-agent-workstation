import { GitBranch, Unplug } from 'lucide-react'
import type { SessionEdgeView, SessionView } from './sessionGraphTypes'
import { formatId, sessionTitle } from './sessionGraphTypes'

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
  const titleById = new Map(sessions.map(session => [session.id, session]))

  return (
    <section className="sg-card">
      <div className="sg-card-header sg-card-header-split">
        <div>
          <GitBranch size={16} />
          <h3>Mounted sources</h3>
        </div>
        <span className="sg-count-pill">{mountedEdges.length}</span>
      </div>
      {mountedEdges.length === 0 ? (
        <p className="sg-muted">No mounted, adapted, or component source edges yet.</p>
      ) : (
        <div className="sg-edge-list">
          {mountedEdges.map(edge => {
            const selected = edge.id === selectedEdgeId
            return (
              <article key={edge.id} className={`sg-edge-row ${selected ? 'is-selected' : ''}`} onClick={() => onSelectEdge?.(edge.id)}>
                <div className="sg-edge-node">
                  <span>{sessionTitle(titleById, edge.source_session_id)}</span>
                  <small>{formatId(edge.source_session_id)}</small>
                </div>
                <code>{edge.type}</code>
                <div className="sg-edge-node">
                  <span>{sessionTitle(titleById, edge.target_session_id)}</span>
                  <small>{formatId(edge.target_session_id)}</small>
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
