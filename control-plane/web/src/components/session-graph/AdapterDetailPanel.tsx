import { ArrowRight, Cable } from 'lucide-react'
import type { SessionView } from './sessionGraphTypes'
import { adapterFacet, formatId, sessionTitle } from './sessionGraphTypes'

export default function AdapterDetailPanel({
  sessions,
  selectedSessionId,
  onSelectSession,
}: {
  sessions: SessionView[]
  selectedSessionId?: string
  onSelectSession?: (sessionId: string) => void
}) {
  const adapters = sessions.filter(session => session.kind === 'adapter')
  const sessionById = new Map(sessions.map(session => [session.id, session]))

  return (
    <section className="sg-card">
      <div className="sg-card-header sg-card-header-split">
        <div>
          <Cable size={16} />
          <h3>Adapter details</h3>
        </div>
        <span className="sg-count-pill">{adapters.length}</span>
      </div>
      {adapters.length === 0 ? (
        <p className="sg-muted">Adapter sessions appear here after non-trivial mounts.</p>
      ) : (
        <div className="sg-adapter-list">
          {adapters.map(session => {
            const facet = adapterFacet(session)
            const mappings = facet.mappings || []
            const selected = session.id === selectedSessionId
            const hasConstraints = Boolean(facet.constraints?.length || facet.non_goals?.length)
            return (
              <article key={session.id} className={`sg-adapter ${selected ? 'is-selected' : ''}`} onClick={() => onSelectSession?.(session.id)}>
                <div className="sg-row-split">
                  <h4>{session.title}</h4>
                  <span className="sg-mini-tag">{mappings.length} mappings</span>
                </div>
                <p className="sg-adapter-route">
                  {facet.source_role || 'source'} <ArrowRight size={12} /> {facet.target_role || 'target'}
                </p>
                <p className="sg-muted sg-small">
                  {sessionTitle(sessionById, facet.source_session_id || '') || formatId(facet.source_session_id || '')}
                  {' → '}
                  {sessionTitle(sessionById, facet.target_session_id || '') || formatId(facet.target_session_id || '')}
                </p>
                <div className="sg-tags">
                  <span>{facet.preservation_mode || 'lossless_reference'}</span>
                  <span>{facet.adaptation_mode || 'semantic_projection'}</span>
                  <span>{facet.mapping_status || 'proposed'}</span>
                </div>
                {mappings.length > 0 && (
                  <details className="sg-details">
                    <summary>Mappings</summary>
                    <div className="sg-mapping-list">
                      {mappings.slice(0, 8).map(mapping => (
                        <div key={mapping.id} className="sg-mapping-row">
                          <div>
                            <strong>{mapping.source.capability || mapping.source.description || 'source'}</strong>
                            <span>{mapping.relationship}</span>
                          </div>
                          <ArrowRight size={12} />
                          <div>
                            <strong>{mapping.target.capability || mapping.target.description || 'target'}</strong>
                            <span>{Math.round((mapping.confidence || 0) * 100)}% · {mapping.status || 'hypothesis'}</span>
                          </div>
                        </div>
                      ))}
                      {mappings.length > 8 && <p className="sg-muted sg-small">{mappings.length - 8} additional mappings hidden.</p>}
                    </div>
                  </details>
                )}
                {hasConstraints && (
                  <details className="sg-details">
                    <summary>Constraints and non-goals</summary>
                    {facet.constraints?.length ? <ul>{facet.constraints.map(item => <li key={item}>{item}</li>)}</ul> : null}
                    {facet.non_goals?.length ? <ul>{facet.non_goals.map(item => <li key={item}>{item}</li>)}</ul> : null}
                  </details>
                )}
              </article>
            )
          })}
        </div>
      )}
    </section>
  )
}
