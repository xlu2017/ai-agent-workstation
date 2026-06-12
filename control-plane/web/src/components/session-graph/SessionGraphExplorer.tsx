import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle, Clock, Database, Eye, Folder, GitBranch, Layers, Network, Play, RefreshCw, Search, ShieldCheck, Unplug } from 'lucide-react'
import MountedSourcesPanel from './MountedSourcesPanel'
import AdapterDetailPanel from './AdapterDetailPanel'
import ContextProjectionPanel from './ContextProjectionPanel'
import SessionGraphCrudPanel from './SessionGraphCrudPanel'
import type { GraphSnapshot, MountResultView, SessionEdgeView, SessionEventView, SessionView } from './sessionGraphTypes'
import { adapterFacet, formatId, sessionTitle } from './sessionGraphTypes'
import './session-graph.css'
import './session-graph-ux.css'

const emptyGraph: GraphSnapshot = { sessions: [], edges: [], events: [], projections: [] }
const mountModes = ['reference', 'component', 'dependency', 'vendor', 'template', 'fork', 'port', 'wrap', 'compare', 'unknown']

interface MountDraft {
  source_session_id: string
  target_session_id: string
  user_intent: string
  mount_mode: string
  create_adaptation_session: boolean
  make_active: boolean
  allow_private_projection: boolean
}

const defaultMountDraft: MountDraft = {
  source_session_id: '',
  target_session_id: '',
  user_intent: '',
  mount_mode: 'reference',
  create_adaptation_session: true,
  make_active: false,
  allow_private_projection: false,
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) } })
  const text = await response.text()
  const data = text ? JSON.parse(text) : {}
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : text || response.statusText)
  return data as T
}

function normalizeGraph(graph?: Partial<GraphSnapshot>): GraphSnapshot {
  return { sessions: graph?.sessions || [], edges: graph?.edges || [], events: graph?.events || [], projections: graph?.projections || [] }
}

function sessionKindOrder(kind: string): number {
  const order = ['container', 'app', 'repo', 'goal', 'work', 'adapter', 'runtime', 'validation', 'question', 'memory', 'artifact', 'pull_request', 'deployment']
  const index = order.indexOf(kind)
  return index === -1 ? order.length : index
}

function JsonPreview({ value }: { value: unknown }) {
  if (!value || (typeof value === 'object' && Object.keys(value as Record<string, unknown>).length === 0)) return <p className="sg-muted sg-small">None.</p>
  return <pre className="sg-json">{JSON.stringify(value, null, 2)}</pre>
}

function SessionWorkflowGuide() {
  return (
    <section className="sg-card sg-workflow-card">
      <div className="sg-card-header sg-card-header-split"><div><CheckCircle size={16} /><h3>Common software development workflow</h3></div><span className="sg-count-pill">graph before execution</span></div>
      <p className="sg-muted">A normal coding task is modeled as durable graph topology first. File edits, commands, screenshots, test runs, and agent actions attach later as events, facets, projections, or artifacts.</p>
      <div className="sg-workflow-steps">
        <div><strong>1</strong><span>Repo session</span><small>Create or select the repo session that owns codebase identity, path, commands, ownership, and capability metadata.</small></div>
        <div><strong>2</strong><span>Goal session</span><small>Create the requested feature, bug fix, refactor, review, or integration as a goal session.</small></div>
        <div><strong>3</strong><span>Mount + adapter</span><small>Mount the repo under the goal and create an adapter/projection when context needs translation or filtering.</small></div>
        <div><strong>4</strong><span>Work session</span><small>Create a work session for the implementation attempt. Plans and user interjections belong here.</small></div>
        <div><strong>5</strong><span>Runtime session</span><small>Create runtime only when actions need a server, terminal, browser, emulator, container, or worktree.</small></div>
        <div><strong>6</strong><span>Validation session</span><small>Represent tests, lint, typecheck, screenshot checks, manual review, and acceptance evidence.</small></div>
        <div><strong>7</strong><span>PR or artifact</span><small>Create a pull_request, deployment, or artifact session for reviewable output and handoff.</small></div>
      </div>
      <div className="sg-workflow-policy">
        <div className="is-ok">Everything durable and user-visible is a graph session.</div>
        <div className="is-warning">Single commands, log lines, file edits, and temporary UI state are not sessions; attach them to the nearest durable session.</div>
      </div>
    </section>
  )
}

function SessionNode({ session, selected, inbound, outbound, onSelect }: { session: SessionView; selected: boolean; inbound: number; outbound: number; onSelect: (id: string) => void }) {
  const facet = session.kind === 'adapter' ? adapterFacet(session) : null
  return (
    <button className={`sg-node ${selected ? 'is-selected' : ''}`} type="button" onClick={() => onSelect(session.id)}>
      <span className="sg-kind">{session.kind}</span>
      <strong>{session.title}</strong>
      <small>{session.status || 'proposed'} · {formatId(session.id)}</small>
      {facet?.mapping_status && <span className="sg-mini-tag">{facet.mapping_status}</span>}
      <span className="sg-node-edges">← {inbound} · {outbound} →</span>
    </button>
  )
}

function GraphCanvas({ sessions, edges, selectedSessionId, selectedEdgeId, onSelectSession, onSelectEdge }: { sessions: SessionView[]; edges: SessionEdgeView[]; selectedSessionId?: string; selectedEdgeId?: string; onSelectSession: (id: string) => void; onSelectEdge: (id: string) => void }) {
  const grouped = useMemo(() => {
    const map = new Map<string, SessionView[]>()
    for (const session of sessions) {
      if (!map.has(session.kind)) map.set(session.kind, [])
      map.get(session.kind)?.push(session)
    }
    return Array.from(map.entries()).sort(([a], [b]) => sessionKindOrder(a) - sessionKindOrder(b)).map(([kind, items]) => [kind, items.sort((a, b) => a.title.localeCompare(b.title))] as const)
  }, [sessions])
  const inboundCount = (sessionId: string) => edges.filter(edge => edge.target_session_id === sessionId).length
  const outboundCount = (sessionId: string) => edges.filter(edge => edge.source_session_id === sessionId).length

  return (
    <div className="sg-graph-canvas">
      {grouped.map(([kind, items]) => (
        <section key={kind} className="sg-graph-column">
          <div className="sg-graph-column-header"><span>{kind}</span><strong>{items.length}</strong></div>
          {items.map(session => <SessionNode key={session.id} session={session} selected={session.id === selectedSessionId} inbound={inboundCount(session.id)} outbound={outboundCount(session.id)} onSelect={onSelectSession} />)}
        </section>
      ))}
      {edges.length > 0 && (
        <section className="sg-edge-strip">
          <div className="sg-graph-column-header"><span>relationships</span><strong>{edges.length}</strong></div>
          {edges.slice(0, 18).map(edge => (
            <button key={edge.id} className={`sg-edge-chip ${edge.id === selectedEdgeId ? 'is-selected' : ''}`} type="button" onClick={() => onSelectEdge(edge.id)}>
              <span>{edge.type}</span><small>{formatId(edge.source_session_id)} → {formatId(edge.target_session_id)}</small>
            </button>
          ))}
        </section>
      )}
    </div>
  )
}

function MountForm({ sessions, draft, setDraft, onPreview, onClear, busy }: { sessions: SessionView[]; draft: MountDraft; setDraft: (draft: MountDraft) => void; onPreview: () => void; onClear: () => void; busy: boolean }) {
  return (
    <section className="sg-card">
      <div className="sg-card-header"><GitBranch size={16} /><h3>Preview mount</h3></div>
      <div className="sg-form-grid">
        <label><span>Source</span><select value={draft.source_session_id} onChange={event => setDraft({ ...draft, source_session_id: event.target.value })}><option value="">Select source session</option>{sessions.map(session => <option key={session.id} value={session.id}>{session.title} · {session.kind}</option>)}</select></label>
        <label><span>Target</span><select value={draft.target_session_id} onChange={event => setDraft({ ...draft, target_session_id: event.target.value })}><option value="">Select target session</option>{sessions.map(session => <option key={session.id} value={session.id}>{session.title} · {session.kind}</option>)}</select></label>
        <label><span>Mount mode</span><select value={draft.mount_mode} onChange={event => setDraft({ ...draft, mount_mode: event.target.value })}>{mountModes.map(mode => <option key={mode} value={mode}>{mode}</option>)}</select></label>
        <label className="sg-form-span"><span>User intent</span><textarea value={draft.user_intent} onChange={event => setDraft({ ...draft, user_intent: event.target.value })} placeholder="Describe why this source should be projected into the target." /></label>
      </div>
      <div className="sg-checkbox-row">
        <label><input type="checkbox" checked={draft.create_adaptation_session} onChange={event => setDraft({ ...draft, create_adaptation_session: event.target.checked })} /> Create adapter session</label>
        <label><input type="checkbox" checked={draft.make_active} onChange={event => setDraft({ ...draft, make_active: event.target.checked })} /> Make target active</label>
        <label><input type="checkbox" checked={draft.allow_private_projection} onChange={event => setDraft({ ...draft, allow_private_projection: event.target.checked })} /> Permit private projection</label>
      </div>
      <div className="sg-form-actions">
        <button className="sg-button sg-button-primary" type="button" onClick={onPreview} disabled={busy || !draft.source_session_id || !draft.target_session_id || !draft.user_intent.trim()}><Eye size={14} /> Preview</button>
        <button className="sg-button" type="button" onClick={onClear} disabled={busy}>Clear</button>
      </div>
    </section>
  )
}

function MountPreviewPanel({ result, onApply, applying }: { result: MountResultView | null; onApply: () => void; applying: boolean }) {
  if (!result) return null
  const checks = result.policy_evidence?.checks || []
  return (
    <section className="sg-card sg-preview-card">
      <div className="sg-card-header sg-card-header-split"><div><Eye size={16} /><h3>Mount preview</h3></div><button className="sg-button sg-button-primary" type="button" onClick={onApply} disabled={applying}><Play size={14} /> Apply mount</button></div>
      {result.warnings.length > 0 && <div className="sg-warning-list">{result.warnings.map(warning => <div key={warning}><AlertTriangle size={14} /> {warning}</div>)}</div>}
      <div className="sg-preview-grid">
        <div><strong>Mounted edge</strong><code>{result.mounted_edge.type}</code><small>{formatId(result.mounted_edge.source_session_id)} → {formatId(result.mounted_edge.target_session_id)}</small></div>
        <div><strong>Adapter</strong><code>{result.adaptation_session?.title || 'none'}</code><small>{result.adaptation_edges.length} adapter edges</small></div>
        <div><strong>Projection</strong><code>{result.context_projection_delta.projection_mode}</code><small>{result.context_projection_delta.budget.max_tokens} tokens · {result.context_projection_delta.budget.max_files} files</small></div>
      </div>
      {checks.length > 0 && <div className="sg-policy-checks">{checks.map(check => <div key={check.code} className={check.ok ? 'is-ok' : 'is-blocked'}><span>{check.ok ? '✓' : '×'}</span><strong>{check.code}</strong><small>{check.message}</small></div>)}</div>}
    </section>
  )
}

function SessionDetail({ session, edges, events }: { session?: SessionView; edges: SessionEdgeView[]; events: SessionEventView[] }) {
  if (!session) return <section className="sg-card"><div className="sg-card-header"><Database size={16} /><h3>Session detail</h3></div><p className="sg-muted">Select a session to inspect facets, policy, edges, and event history.</p></section>
  const relatedEdges = edges.filter(edge => edge.source_session_id === session.id || edge.target_session_id === session.id)
  const relatedEvents = events.filter(event => event.session_id === session.id || event.root_session_id === session.id)
  return (
    <section className="sg-card">
      <div className="sg-card-header sg-card-header-split"><div><Database size={16} /><h3>Session detail</h3></div><span className="sg-kind">{session.kind}</span></div>
      <h4 className="sg-detail-title">{session.title}</h4>
      {session.summary && <p className="sg-muted">{session.summary}</p>}
      <div className="sg-detail-grid"><div><strong>Status</strong><span>{session.status || 'proposed'}</span></div><div><strong>Session id</strong><span>{formatId(session.id)}</span></div><div><strong>Root</strong><span>{session.root_id ? formatId(session.root_id) : 'none'}</span></div><div><strong>Edges</strong><span>{relatedEdges.length}</span></div></div>
      <details className="sg-details" open><summary>Policy</summary><JsonPreview value={session.policy} /></details>
      <details className="sg-details"><summary>Facets</summary><JsonPreview value={session.facets} /></details>
      <details className="sg-details"><summary>Recent events</summary>{relatedEvents.length === 0 ? <p className="sg-muted sg-small">No events for this session.</p> : relatedEvents.slice(-6).map(event => <div key={event.id} className="sg-event-row"><Clock size={13} /><span>{event.type}</span><small>{event.created_at || formatId(event.id)}</small></div>)}</details>
    </section>
  )
}

export default function SessionGraphExplorer() {
  const [graph, setGraph] = useState<GraphSnapshot>(emptyGraph)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [selectedSessionId, setSelectedSessionId] = useState<string | undefined>()
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | undefined>()
  const [search, setSearch] = useState('')
  const [kindFilter, setKindFilter] = useState('all')
  const [mountDraft, setMountDraft] = useState<MountDraft>(defaultMountDraft)
  const [previewResult, setPreviewResult] = useState<MountResultView | null>(null)

  const refresh = useCallback(() => {
    setLoading(true)
    setError('')
    apiFetch<{ graph: GraphSnapshot }>('/api/session-graph/snapshot')
      .then(data => {
        const next = normalizeGraph(data.graph)
        setGraph(next)
        setSelectedSessionId(previous => previous && next.sessions.some(session => session.id === previous) ? previous : next.sessions[0]?.id)
        setSelectedEdgeId(previous => previous && next.edges.some(edge => edge.id === previous) ? previous : undefined)
      })
      .catch(err => setError((err as Error).message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const sessionById = useMemo(() => new Map(graph.sessions.map(session => [session.id, session])), [graph.sessions])
  const kinds = useMemo(() => Array.from(new Set(graph.sessions.map(session => session.kind))).sort((a, b) => sessionKindOrder(a) - sessionKindOrder(b)), [graph.sessions])
  const filteredSessions = useMemo(() => {
    const query = search.trim().toLowerCase()
    return graph.sessions.filter(session => (kindFilter === 'all' || session.kind === kindFilter) && (!query || `${session.title} ${session.summary || ''} ${session.id}`.toLowerCase().includes(query)))
  }, [graph.sessions, kindFilter, search])
  const visibleSessionIds = useMemo(() => new Set(filteredSessions.map(session => session.id)), [filteredSessions])
  const visibleEdges = useMemo(() => graph.edges.filter(edge => visibleSessionIds.has(edge.source_session_id) && visibleSessionIds.has(edge.target_session_id)), [graph.edges, visibleSessionIds])
  const selectedSession = selectedSessionId ? sessionById.get(selectedSessionId) : undefined
  const selectedEdge = selectedEdgeId ? graph.edges.find(edge => edge.id === selectedEdgeId) : undefined
  const adapterCount = graph.sessions.filter(session => session.kind === 'adapter').length
  const mountedCount = graph.edges.filter(edge => edge.type === 'mounted_under').length

  function buildMountBody() {
    return {
      source_session_id: mountDraft.source_session_id,
      target_session_id: mountDraft.target_session_id,
      user_intent: mountDraft.user_intent.trim(),
      mount_mode: mountDraft.mount_mode,
      create_adaptation_session: mountDraft.create_adaptation_session,
      make_active: mountDraft.make_active,
      authorization: mountDraft.allow_private_projection ? { allow_private_projection: true, authorized_by: 'session-graph-ui', reason: 'Approved from session graph UI.', grants: ['private_projection'] } : null,
    }
  }

  async function previewMount() {
    if (mountDraft.source_session_id === mountDraft.target_session_id) { setError('Source and target must be different sessions.'); return }
    setBusy(true); setError('')
    try {
      const data = await apiFetch<{ result: MountResultView }>('/api/session-graph/mount/preview', { method: 'POST', body: JSON.stringify(buildMountBody()) })
      setPreviewResult(data.result)
      setSelectedEdgeId(data.result.mounted_edge.id)
    } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }

  async function applyMount() {
    setBusy(true); setError('')
    try {
      const data = await apiFetch<{ result: MountResultView }>('/api/session-graph/mount', { method: 'POST', body: JSON.stringify(buildMountBody()) })
      setPreviewResult(data.result)
      setSelectedSessionId(data.result.adaptation_session?.id || data.result.mounted_edge.target_session_id)
      refresh()
    } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }

  async function unmount(edge: SessionEdgeView) {
    setBusy(true); setError('')
    try {
      await apiFetch('/api/session-graph/unmount', { method: 'POST', body: JSON.stringify({ source_session_id: edge.source_session_id, target_session_id: edge.target_session_id, reason: 'Unmounted from session graph UI.', remove_adapter_edges: false }) })
      setSelectedEdgeId(undefined); setPreviewResult(null); refresh()
    } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }

  return (
    <div className="sg-page">
      <header className="sg-header"><div><div className="sg-eyebrow"><Layers size={14} /> Session graph</div><h2>Everything durable is a session</h2><p>Model the development workflow as graph sessions first, then attach actions, events, and projected context before execution.</p></div><button className="sg-button" onClick={refresh} disabled={loading || busy}><RefreshCw size={14} /> Refresh</button></header>
      {error && <div className="sg-error"><AlertTriangle size={15} /> {error}</div>}
      <div className="sg-summary"><div><strong>{graph.sessions.length}</strong><span>sessions</span></div><div><strong>{graph.edges.length}</strong><span>edges</span></div><div><strong>{graph.projections.length}</strong><span>projections</span></div><div><strong>{adapterCount}</strong><span>adapters</span></div><div><strong>{mountedCount}</strong><span>mounts</span></div><div><strong>{graph.events.length}</strong><span>events</span></div></div>
      <div className="sg-toolbar sg-card"><label className="sg-search"><Search size={15} /><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Search sessions by title, summary, or id" /></label><label><span>Kind</span><select value={kindFilter} onChange={event => setKindFilter(event.target.value)}><option value="all">All kinds</option>{kinds.map(kind => <option key={kind} value={kind}>{kind}</option>)}</select></label></div>
      <div className="sg-layout">
        <main className="sg-main-stack">
          <SessionWorkflowGuide />
          <SessionGraphCrudPanel sessions={graph.sessions} edges={graph.edges} selectedSession={selectedSession} selectedEdgeId={selectedEdgeId} onRefresh={refresh} onSelectSession={setSelectedSessionId} />
          <section className="sg-card sg-main-card"><div className="sg-card-header sg-card-header-split"><div><Network size={16} /><h3>Graph canvas</h3></div><span className="sg-count-pill">{filteredSessions.length} visible</span></div>{loading ? <p className="sg-muted">Loading session graph...</p> : graph.sessions.length === 0 ? <p className="sg-muted">No graph sessions have been persisted yet. Create repo and goal sessions, mount the repo under the goal, then add work, runtime, validation, and PR sessions as the task progresses.</p> : <GraphCanvas sessions={filteredSessions} edges={visibleEdges} selectedSessionId={selectedSessionId} selectedEdgeId={selectedEdgeId} onSelectSession={setSelectedSessionId} onSelectEdge={setSelectedEdgeId} />}</section>
          <MountForm sessions={graph.sessions} draft={mountDraft} setDraft={setMountDraft} onPreview={previewMount} onClear={() => { setMountDraft(defaultMountDraft); setPreviewResult(null) }} busy={busy} />
          <MountPreviewPanel result={previewResult} onApply={applyMount} applying={busy} />
        </main>
        <aside className="sg-side">
          <SessionDetail session={selectedSession} edges={graph.edges} events={graph.events} />
          {selectedEdge && <section className="sg-card"><div className="sg-card-header sg-card-header-split"><div><GitBranch size={16} /><h3>Edge detail</h3></div>{selectedEdge.type === 'mounted_under' && <button className="sg-button sg-button-danger" type="button" onClick={() => unmount(selectedEdge)} disabled={busy}><Unplug size={13} /> Unmount</button>}</div><div className="sg-detail-grid"><div><strong>Type</strong><span>{selectedEdge.type}</span></div><div><strong>Source</strong><span>{sessionTitle(sessionById, selectedEdge.source_session_id)}</span></div><div><strong>Target</strong><span>{sessionTitle(sessionById, selectedEdge.target_session_id)}</span></div><div><strong>ID</strong><span>{formatId(selectedEdge.id)}</span></div></div><JsonPreview value={selectedEdge.metadata} /></section>}
          <MountedSourcesPanel sessions={graph.sessions} edges={graph.edges} selectedEdgeId={selectedEdgeId} onSelectEdge={setSelectedEdgeId} onUnmount={unmount} busy={busy} />
          <AdapterDetailPanel sessions={graph.sessions} selectedSessionId={selectedSessionId} onSelectSession={setSelectedSessionId} />
          <ContextProjectionPanel projections={graph.projections} sessions={graph.sessions} selectedSessionId={selectedSessionId} previewProjection={previewResult?.context_projection_delta || null} />
          <section className="sg-card"><div className="sg-card-header"><ShieldCheck size={16} /><h3>Recent events</h3></div>{graph.events.length === 0 ? <p className="sg-muted">No session events yet.</p> : graph.events.slice(-8).reverse().map(event => <div key={event.id} className="sg-event-row"><Clock size={13} /><span>{event.type}</span><small>{event.created_at || formatId(event.id)}</small></div>)}</section>
        </aside>
      </div>
    </div>
  )
}
