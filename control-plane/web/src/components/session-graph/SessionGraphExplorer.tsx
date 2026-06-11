import { useCallback, useEffect, useState } from 'react'
import { Layers, RefreshCw } from 'lucide-react'
import MountedSourcesPanel, { SessionEdgeView, SessionView } from './MountedSourcesPanel'
import AdapterDetailPanel from './AdapterDetailPanel'
import ContextProjectionPanel, { ProjectionView } from './ContextProjectionPanel'
import './session-graph.css'

interface GraphSnapshot {
  sessions: SessionView[]
  edges: SessionEdgeView[]
  projections: ProjectionView[]
}

const emptyGraph: GraphSnapshot = { sessions: [], edges: [], projections: [] }

export default function SessionGraphExplorer() {
  const [graph, setGraph] = useState<GraphSnapshot>(emptyGraph)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const refresh = useCallback(() => {
    setLoading(true)
    setError('')
    fetch('/api/session-graph/snapshot')
      .then(async response => {
        if (!response.ok) throw new Error(await response.text())
        return response.json() as Promise<{ graph: GraphSnapshot }>
      })
      .then(data => setGraph(data.graph || emptyGraph))
      .catch(err => setError((err as Error).message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { refresh() }, [refresh])

  return (
    <div className="sg-page">
      <header className="sg-header">
        <div>
          <div className="sg-eyebrow"><Layers size={14} /> Session graph</div>
          <h2>Everything is a session</h2>
          <p>Explore app, repo, goal, work, mount, and adapter sessions without rewriting source history.</p>
        </div>
        <button className="sg-button" onClick={refresh} disabled={loading}>
          <RefreshCw size={14} /> Refresh
        </button>
      </header>

      {error && <div className="sg-error">{error}</div>}

      <div className="sg-summary">
        <div><strong>{graph.sessions.length}</strong><span>sessions</span></div>
        <div><strong>{graph.edges.length}</strong><span>edges</span></div>
        <div><strong>{graph.projections.length}</strong><span>projections</span></div>
      </div>

      <div className="sg-layout">
        <section className="sg-card sg-main-card">
          <div className="sg-card-header">
            <Layers size={16} />
            <h3>Session explorer</h3>
          </div>
          {loading ? (
            <p className="sg-muted">Loading session graph...</p>
          ) : graph.sessions.length === 0 ? (
            <p className="sg-muted">No graph sessions have been persisted yet. Use the API scaffold to create or mount sessions.</p>
          ) : (
            <div className="sg-session-list">
              {graph.sessions.map(session => (
                <article key={session.id} className="sg-session">
                  <div>
                    <span className="sg-kind">{session.kind}</span>
                    <h4>{session.title}</h4>
                    {session.summary && <p>{session.summary}</p>}
                  </div>
                  <div className="sg-session-actions">
                    <button>View original session</button>
                    <button>View adapted projection</button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>

        <aside className="sg-side">
          <MountedSourcesPanel sessions={graph.sessions} edges={graph.edges} />
          <AdapterDetailPanel sessions={graph.sessions} />
          <ContextProjectionPanel projections={graph.projections} />
        </aside>
      </div>
    </div>
  )
}
