export interface SessionPolicyView {
  visibility?: string
  allow_mount?: boolean
  allow_adapt?: boolean
  allow_outbound_mount?: boolean
  allow_inbound_mount?: boolean
  allow_outbound_adapt?: boolean
  allow_inbound_adapt?: boolean
  license?: string | null
  security_constraints?: string[]
}

export interface SessionView {
  id: string
  kind: string
  title: string
  summary?: string
  status?: string
  parent_id?: string | null
  root_id?: string | null
  facets?: Record<string, unknown>
  policy?: SessionPolicyView
  state?: Record<string, unknown>
  metadata?: Record<string, unknown>
  created_at?: string
  updated_at?: string
}

export interface SessionEdgeView {
  id: string
  type: string
  source_session_id: string
  target_session_id: string
  metadata?: Record<string, unknown>
  created_at?: string
  created_from_event_id?: string | null
}

export interface ProjectionBudgetView {
  max_tokens: number
  max_files: number
  max_events: number
  recency_days?: number
}

export interface ProjectionView {
  id: string
  active_session_id: string
  source_session_ids: string[]
  projection_mode: string
  projection_source?: string
  relevance_score?: number
  evidence?: string[]
  include_selectors: string[]
  exclude_selectors: string[]
  budget: ProjectionBudgetView
  rationale: string
}

export interface SessionEventView {
  id: string
  type: string
  session_id: string
  root_session_id?: string | null
  actor?: string
  data?: Record<string, unknown>
  created_at?: string
}

export interface GraphSnapshot {
  sessions: SessionView[]
  edges: SessionEdgeView[]
  events: SessionEventView[]
  projections: ProjectionView[]
}

export interface AdapterEndpointView {
  session_id: string
  facet?: string
  path?: string
  symbol?: string
  endpoint?: string
  capability?: string
  description?: string
}

export interface AdapterMappingView {
  id: string
  source: AdapterEndpointView
  target: AdapterEndpointView
  relationship: string
  confidence: number
  evidence?: string[]
  status?: string
}

export interface AdapterFacetView {
  source_session_id?: string
  target_session_id?: string
  source_role?: string
  target_role?: string
  preservation_mode?: string
  adaptation_mode?: string
  mapping_status?: string
  mappings?: AdapterMappingView[]
  constraints?: string[]
  non_goals?: string[]
}

export interface PolicyCheckEvidenceView {
  code: string
  ok: boolean
  message: string
  source_session_id?: string
  target_session_id?: string
}

export interface PolicyEvidenceView {
  source_policy_source_ids?: string[]
  target_policy_source_ids?: string[]
  checks?: PolicyCheckEvidenceView[]
  authorization?: Record<string, unknown> | null
}

export interface MountResultView {
  mounted_edge: SessionEdgeView
  adaptation_session?: SessionView | null
  adaptation_edges: SessionEdgeView[]
  context_projection_delta: ProjectionView
  policy_evidence: PolicyEvidenceView
  warnings: string[]
  events: SessionEventView[]
}

export function adapterFacet(session: SessionView): AdapterFacetView {
  const adapter = session.facets?.adapter
  if (adapter && typeof adapter === 'object') return adapter as AdapterFacetView
  return {}
}

export function formatId(id: string): string {
  if (id.length <= 22) return id
  return `${id.slice(0, 10)}…${id.slice(-8)}`
}

export function sessionTitle(sessionById: Map<string, SessionView>, sessionId: string): string {
  return sessionById.get(sessionId)?.title || sessionId
}
