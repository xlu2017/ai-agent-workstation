import { FileText } from 'lucide-react'

export interface ProjectionView {
  id: string
  active_session_id: string
  source_session_ids: string[]
  projection_mode: string
  include_selectors: string[]
  exclude_selectors: string[]
  budget: {
    max_tokens: number
    max_files: number
    max_events: number
    recency_days?: number
  }
  rationale: string
}

export default function ContextProjectionPanel({ projections }: { projections: ProjectionView[] }) {
  const latest = projections[projections.length - 1]

  return (
    <section className="sg-card">
      <div className="sg-card-header">
        <FileText size={16} />
        <h3>Context projection</h3>
      </div>
      {!latest ? (
        <p className="sg-muted">Mount previews and applied mounts will show projection rules here.</p>
      ) : (
        <div className="sg-projection">
          <div className="sg-tags">
            <span>{latest.projection_mode}</span>
            <span>{latest.budget.max_tokens} tokens</span>
            <span>{latest.budget.max_files} files</span>
            <span>{latest.budget.max_events} events</span>
          </div>
          <p>{latest.rationale}</p>
          <div className="sg-selector-grid">
            <div>
              <strong>Include</strong>
              <ul>{latest.include_selectors.map(selector => <li key={selector}>{selector}</li>)}</ul>
            </div>
            <div>
              <strong>Exclude</strong>
              <ul>{latest.exclude_selectors.map(selector => <li key={selector}>{selector}</li>)}</ul>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
