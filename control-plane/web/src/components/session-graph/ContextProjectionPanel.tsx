import { FileText } from 'lucide-react'
import type { ProjectionView, SessionView } from './sessionGraphTypes'
import { formatId, sessionTitle } from './sessionGraphTypes'

export default function ContextProjectionPanel({
  projections,
  sessions,
  selectedSessionId,
  previewProjection,
}: {
  projections: ProjectionView[]
  sessions: SessionView[]
  selectedSessionId?: string
  previewProjection?: ProjectionView | null
}) {
  const sessionById = new Map(sessions.map(session => [session.id, session]))
  const scoped = selectedSessionId
    ? projections.filter(projection => projection.active_session_id === selectedSessionId || projection.source_session_ids.includes(selectedSessionId))
    : projections
  const latest = previewProjection || scoped[scoped.length - 1] || projections[projections.length - 1]

  return (
    <section className="sg-card">
      <div className="sg-card-header sg-card-header-split">
        <div>
          <FileText size={16} />
          <h3>{previewProjection ? 'Preview projection' : 'Context projection'}</h3>
        </div>
        <span className="sg-count-pill">{scoped.length}</span>
      </div>
      {!latest ? (
        <p className="sg-muted">Mount previews and applied mounts will show projection rules here.</p>
      ) : (
        <div className="sg-projection">
          <div className="sg-tags">
            <span>{latest.projection_mode}</span>
            <span>{latest.projection_source || 'heuristic'}</span>
            {typeof latest.relevance_score === 'number' && <span>{Math.round(latest.relevance_score * 100)}% relevance</span>}
          </div>
          <div className="sg-budget-grid">
            <div><strong>{latest.budget.max_tokens}</strong><span>tokens</span></div>
            <div><strong>{latest.budget.max_files}</strong><span>files</span></div>
            <div><strong>{latest.budget.max_events}</strong><span>events</span></div>
            <div><strong>{latest.budget.recency_days || 'any'}</strong><span>days</span></div>
          </div>
          <p>{latest.rationale}</p>
          <div className="sg-projection-scope">
            <div>
              <strong>Active</strong>
              <span>{sessionTitle(sessionById, latest.active_session_id)}</span>
              <small>{formatId(latest.active_session_id)}</small>
            </div>
            <div>
              <strong>Sources</strong>
              {latest.source_session_ids.map(id => (
                <span key={id}>{sessionTitle(sessionById, id)} <small>{formatId(id)}</small></span>
              ))}
            </div>
          </div>
          <div className="sg-selector-grid">
            <div>
              <strong>Include</strong>
              {latest.include_selectors.length === 0 ? <p className="sg-muted sg-small">No include selectors.</p> : <ul>{latest.include_selectors.map(selector => <li key={selector}>{selector}</li>)}</ul>}
            </div>
            <div>
              <strong>Exclude</strong>
              {latest.exclude_selectors.length === 0 ? <p className="sg-muted sg-small">No exclude selectors.</p> : <ul>{latest.exclude_selectors.map(selector => <li key={selector}>{selector}</li>)}</ul>}
            </div>
          </div>
          {latest.evidence?.length ? (
            <details className="sg-details">
              <summary>Evidence</summary>
              <ul>{latest.evidence.map(item => <li key={item}>{item}</li>)}</ul>
            </details>
          ) : null}
        </div>
      )}
    </section>
  )
}
