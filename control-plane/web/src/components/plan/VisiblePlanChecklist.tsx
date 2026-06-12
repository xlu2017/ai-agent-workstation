import { CheckCircle2, Circle, GitBranch, PauseCircle, RefreshCw, XCircle } from 'lucide-react'
import './visible-plan-checklist.css'

export type VisiblePlanStepStatus = 'planned' | 'active' | 'completed' | 'skipped' | 'blocked' | 'superseded'

export interface VisiblePlanStep {
  id: string
  title: string
  action_name?: string
  status: VisiblePlanStepStatus
  completed_by_outcome_id?: string
  completed_at?: string
  evidence?: string[]
}

export interface VisiblePlanArtifact {
  id: string
  session_id: string
  goal: string
  status: 'active' | 'completed' | 'stale' | 'superseded'
  steps: VisiblePlanStep[]
  assumptions?: string[]
  updated_at?: string
}

function StepIcon({ status }: { status: VisiblePlanStepStatus }) {
  if (status === 'completed') return <CheckCircle2 size={16} className="vp-ok" />
  if (status === 'blocked') return <XCircle size={16} className="vp-bad" />
  if (status === 'active') return <RefreshCw size={16} className="vp-active" />
  if (status === 'skipped' || status === 'superseded') return <PauseCircle size={16} className="vp-muted" />
  return <Circle size={16} className="vp-muted" />
}

export default function VisiblePlanChecklist({ plan }: { plan: VisiblePlanArtifact | null }) {
  if (!plan) {
    return <section className="vp-card"><div className="vp-header"><GitBranch size={16} /><h3>Plan</h3></div><p className="vp-muted">No visible plan has been generated for this session yet.</p></section>
  }

  const completed = plan.steps.filter(step => step.status === 'completed').length
  const progress = Math.round((completed / Math.max(plan.steps.length, 1)) * 100)

  return (
    <section className="vp-card">
      <div className="vp-header vp-header-split"><div><GitBranch size={16} /><h3>Plan</h3></div><span className={`vp-status is-${plan.status}`}>{plan.status}</span></div>
      <h4>{plan.goal}</h4>
      <div className="vp-progress"><div style={{ width: `${progress}%` }} /></div>
      <p className="vp-muted">{completed} of {plan.steps.length} planned steps completed. Steps are checkmarked after matching action outcomes are recorded.</p>
      <ol className="vp-steps">
        {plan.steps.map(step => <li key={step.id} className={`vp-step is-${step.status}`}><StepIcon status={step.status} /><div><strong>{step.title}</strong>{step.action_name && <code>{step.action_name}</code>}{step.completed_at && <small>Completed {step.completed_at}</small>}{step.evidence?.slice(0, 2).map(item => <small key={item}>{item}</small>)}</div></li>)}
      </ol>
      {plan.assumptions && plan.assumptions.length > 0 && <details className="vp-assumptions"><summary>Assumptions</summary>{plan.assumptions.map(item => <p key={item}>{item}</p>)}</details>}
    </section>
  )
}
