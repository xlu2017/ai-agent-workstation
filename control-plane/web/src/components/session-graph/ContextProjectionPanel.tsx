import { FileText, Info, Target } from 'lucide-react'
import type { ProjectionView, SessionView } from './sessionGraphTypes'
import { formatId, sessionTitle } from './sessionGraphTypes'
import { parseProjectionBudgetDecision } from './projectionBudgetDecision'
import './projection-budget-decision.css'

function budgetLabel(value: number | undefined, fallback = 'any'): string {
  if (value === undefined || value === null) return fallback
  return new Intl.NumberFormat().format(value)
}

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
  const isPreview = Boolean(previewProjection)
  const budgetDecision = latest ? parseProjectionBudgetDecision(latest) : null

  return (
    <section className={`sg-card ${isPreview ? 'sg-preview-card' : ''}`}>
      <div className="sg-card-header sg-card-header-split">
        <div>
          <FileText size={16} />
          <h3>{isPreview ? 'Preview projection' : 'Context projection'}</h3>
        </div>
        <span className="sg-count-pill">{scoped.length}</span>
      </div>

      <p className="sg-muted sg-small">
        Projection explains exactly how much source context can enter the active session. This is the guardrail against context pollution.
      </p>

      {!latest || !budgetDecision ? (
        <div className="sg-empty-state">
          <Info size={16} />
          <div>
            <strong>No projection yet.</strong>
            <p className="sg-muted sg-small">Preview or apply a mount to see token, file, event, and recency budgets before execution.</p>
          </div>
        </div>
      ) : (
        <div className="sg-projection">
          <div className="sg-tags">
            <span>{latest.projection_mode}</span>
            <span>{latest.projection_source || 'heuristic'}</span>
            <span>{budgetDecision.profile}</span>
            {isPreview && <span>preview</span>}
            {typeof latest.relevance_score === 'number' && <span>{Math.round(latest.relevance_score * 100)}% relevance</span>}
          </div>

          <div className="sg-budget-grid">
            <div><strong>{budgetLabel(latest.budget.max_tokens)}</strong><span>tokens</span></div>
            <div><strong>{budgetLabel(latest.budget.max_files)}</strong><span>files</span></div>
            <div><strong>{budgetLabel(latest.budget.max_events)}</strong><span>events</span></div>
            <div><strong>{latest.budget.recency_days || 'any'}</strong><span>days</span></div>
          </div>

          <div className="sg-budget-decision">
            <div className="sg-budget-decision-header">
              <div className="sg-budget-decision-title">
                <strong>{budgetDecision.title}</strong>
                <small>{budgetDecision.intent}</small>
              </div>
              <span className="sg-count-pill">{budgetLabel(budgetDecision.tokens)} tokens</span>
            </div>
            <p>{budgetDecision.rationale}</p>
            <div className="sg-tags">
              <span>{budgetLabel(budgetDecision.files)} files</span>
              <span>{budgetLabel(budgetDecision.events)} events</span>
              <span>{budgetDecision.recencyDays || 'any'} day lookback</span>
              {budgetDecision.dominanceGuard && <span>dominance guard</span>}
            </div>
            <div className="sg-budget-edit-hint">{budgetDecision.editHint}</div>
          </div>

          <div className="sg-policy-checks">
            <div className="is-ok">
              <Target size={13} />
              <strong>Projection is bounded</strong>
              <small>{latest.rationale}</small>
            </div>
          </div>

          <div className="sg-projection-scope">
            <div>
              <strong>Active session</strong>
              <span>{sessionTitle(sessionById, latest.active_session_id)}</span>
              <small>{formatId(latest.active_session_id)}</small>
            </div>
            <div>
              <strong>Source sessions</strong>
              {latest.source_session_ids.length === 0 ? <span>None</span> : latest.source_session_ids.map(id => (
                <span key={id}>{sessionTitle(sessionById, id)} <small>{formatId(id)}</small></span>
              ))}
            </div>
          </div>

          <div className="sg-selector-grid">
            <div>
              <strong>Include selectors</strong>
              {latest.include_selectors.length === 0 ? <p className="sg-muted sg-small">No include selectors.</p> : <ul>{latest.include_selectors.map(selector => <li key={selector}>{selector}</li>)}</ul>}
            </div>
            <div>
              <strong>Exclude selectors</strong>
              {latest.exclude_selectors.length === 0 ? <p className="sg-muted sg-small">No exclude selectors.</p> : <ul>{latest.exclude_selectors.map(selector => <li key={selector}>{selector}</li>)}</ul>}
            </div>
          </div>

          {latest.evidence?.length ? (
            <details className="sg-details">
              <summary>Why these sources?</summary>
              <ul>{latest.evidence.map(item => <li key={item}>{item}</li>)}</ul>
            </details>
          ) : null}
        </div>
      )}
    </section>
  )
}
