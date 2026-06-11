import { ArrowRight, Cable } from 'lucide-react'
import type { SessionView } from './MountedSourcesPanel'

interface AdapterFacetView {
  source_session_id?: string
  target_session_id?: string
  source_role?: string
  target_role?: string
  preservation_mode?: string
  adaptation_mode?: string
  mapping_status?: string
}

function adapterFacet(session: SessionView): AdapterFacetView {
  const facets = session.facets as Record<string, unknown> | undefined
  const adapter = facets?.adapter
  if (adapter && typeof adapter === 'object') return adapter as AdapterFacetView
  return {}
}

export default function AdapterDetailPanel({ sessions }: { sessions: SessionView[] }) {
  const adapters = sessions.filter(session => session.kind === 'adapter')

  return (
    <section className="sg-card">
      <div className="sg-card-header">
        <Cable size={16} />
        <h3>Adapter details</h3>
      </div>
      {adapters.length === 0 ? (
        <p className="sg-muted">Adapter sessions will appear here after non-trivial mounts.</p>
      ) : (
        <div className="sg-adapter-list">
          {adapters.map(session => {
            const facet = adapterFacet(session)
            return (
              <article key={session.id} className="sg-adapter">
                <h4>{session.title}</h4>
                <p>{facet.source_role || 'source'} <ArrowRight size={12} /> {facet.target_role || 'target'}</p>
                <div className="sg-tags">
                  <span>{facet.preservation_mode || 'lossless_reference'}</span>
                  <span>{facet.adaptation_mode || 'semantic_projection'}</span>
                  <span>{facet.mapping_status || 'proposed'}</span>
                </div>
              </article>
            )
          })}
        </div>
      )}
    </section>
  )
}
