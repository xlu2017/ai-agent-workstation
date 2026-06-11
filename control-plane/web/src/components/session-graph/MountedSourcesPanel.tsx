import { GitBranch } from 'lucide-react'

export interface SessionEdgeView {
  id: string
  type: string
  source_session_id: string
  target_session_id: string
}

export interface SessionView {
  id: string
  kind: string
  title: string
  summary?: string
  facets?: Record<string, unknown>
}

export default function MountedSourcesPanel({
  sessions,
  edges,
}: {
  sessions: SessionView[]
  edges: SessionEdgeView[]
}) {
  const mountedEdges = edges.filter(edge => edge.type === 'mounted_under' || edge.type === 'component_of')
  const titleById = new Map(sessions.map(session => [session.id, session.title]))

  return (
    <section className="sg-card">
      <div className="sg-card-header">
        <GitBranch size={16} />
        <h3>Mounted sources</h3>
      </div>
      {mountedEdges.length === 0 ? (
        <p className="sg-muted">No mounted or component source edges yet.</p>
      ) : (
        <div className="sg-edge-list">
          {mountedEdges.map(edge => (
            <div key={edge.id} className="sg-edge-row">
              <span>{titleById.get(edge.source_session_id) || edge.source_session_id}</span>
              <code>{edge.type}</code>
              <span>{titleById.get(edge.target_session_id) || edge.target_session_id}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
