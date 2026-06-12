import type { ProjectionView } from './sessionGraphTypes'

export interface BudgetProfileCopy {
  title: string
  intent: string
  editHint: string
}

export interface ProjectionBudgetDecisionView {
  profile: string
  title: string
  intent: string
  editHint: string
  rationale: string
  tokens: number
  files: number
  events: number
  recencyDays?: number
  dominanceGuard: boolean
}

// Front-end editable budget copy.
// Change labels and explanations here without touching backend projection logic.
export const BUDGET_PROFILE_COPY: Record<string, BudgetProfileCopy> = {
  direct_ui_action: {
    title: 'Direct UI action',
    intent: 'Use only immediate UI state, success criteria, and the most recent events.',
    editHint: 'Edit this copy when direct browser or desktop actions need different UX wording.',
  },
  known_repo_bug_fix: {
    title: 'Known-area bug fix',
    intent: 'Keep likely files, commands, recent failures, and validation criteria in scope.',
    editHint: 'Edit this copy when bug-fix workflows need different guidance.',
  },
  architecture_planning: {
    title: 'Architecture planning',
    intent: 'Allow broad structure, relationships, interfaces, known paths, and API contracts.',
    editHint: 'Edit this copy when planning sessions need different framing.',
  },
  cross_repo_integration: {
    title: 'Cross-repo integration',
    intent: 'Carry selected interface files, adapter mappings, contracts, constraints, and recent failures.',
    editHint: 'Edit this copy when integration or adapter workflows need different guidance.',
  },
  focused_mount_projection: {
    title: 'Focused mount projection',
    intent: 'Expose only the capabilities needed by the active goal so the mounted source does not dominate it.',
    editHint: 'Edit this copy when focused mounted-session behavior needs different wording.',
  },
  general_session_context: {
    title: 'General session context',
    intent: 'Use summaries, facets, and relationships when no narrower task profile applies.',
    editHint: 'Edit this copy when the default projection needs different explanation.',
  },
}

const DEFAULT_PROFILE_COPY: BudgetProfileCopy = {
  title: 'Budget decision',
  intent: 'Use the numeric projection budget emitted by the backend.',
  editHint: 'Add this profile key to BUDGET_PROFILE_COPY to customize the front-end display.',
}

function evidenceValue(evidence: string[] | undefined, key: string): string | undefined {
  const prefix = `${key}:`
  const match = evidence?.find(item => item.startsWith(prefix))
  return match ? match.slice(prefix.length) : undefined
}

function evidenceNumber(evidence: string[] | undefined, key: string, fallback: number): number {
  const raw = evidenceValue(evidence, key)
  if (!raw) return fallback
  const parsed = Number(raw)
  return Number.isFinite(parsed) ? parsed : fallback
}

export function parseProjectionBudgetDecision(projection: ProjectionView): ProjectionBudgetDecisionView {
  const evidence = projection.evidence || []
  const profile = evidenceValue(evidence, 'budget_profile') || 'general_session_context'
  const copy = BUDGET_PROFILE_COPY[profile] || DEFAULT_PROFILE_COPY
  const rationale = evidenceValue(evidence, 'budget_rationale') || projection.rationale

  return {
    profile,
    title: copy.title,
    intent: copy.intent,
    editHint: copy.editHint,
    rationale,
    tokens: evidenceNumber(evidence, 'budget_tokens', projection.budget.max_tokens),
    files: evidenceNumber(evidence, 'budget_files', projection.budget.max_files),
    events: evidenceNumber(evidence, 'budget_events', projection.budget.max_events),
    recencyDays: evidenceNumber(evidence, 'budget_recency_days', projection.budget.recency_days || 0) || projection.budget.recency_days,
    dominanceGuard: evidence.includes('dominance_guard:broad_source_under_focused_target'),
  }
}
