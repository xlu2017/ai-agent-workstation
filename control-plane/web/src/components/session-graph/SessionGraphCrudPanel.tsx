import { useEffect, useMemo, useState } from 'react'
import { Copy, Edit3, GitBranch, Plus, RefreshCw, Trash2 } from 'lucide-react'
import type { SessionEdgeView, SessionView } from './sessionGraphTypes'

const sessionKinds = ['app', 'repo', 'goal', 'work', 'question', 'validation', 'adapter', 'runtime', 'memory', 'artifact', 'container']
const sessionStatuses = ['proposed', 'active', 'paused', 'blocked', 'completed', 'cancelled', 'archived']
const edgeTypes = ['contains', 'references', 'depends_on', 'blocks', 'implements', 'validates', 'produces', 'consumes', 'mounted_under', 'adapted_under', 'component_of', 'sibling_of']

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) } })
  const text = await response.text()
  const data = text ? JSON.parse(text) : {}
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : text || response.statusText)
  return data as T
}

export default function SessionGraphCrudPanel({
  sessions,
  edges,
  selectedSession,
  selectedEdgeId,
  onRefresh,
  onSelectSession,
}: {
  sessions: SessionView[]
  edges: SessionEdgeView[]
  selectedSession?: SessionView
  selectedEdgeId?: string
  onRefresh: () => void
  onSelectSession: (id: string) => void
}) {
  const selectedEdge = useMemo(() => edges.find(edge => edge.id === selectedEdgeId), [edges, selectedEdgeId])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const [newKind, setNewKind] = useState('goal')
  const [newTitle, setNewTitle] = useState('')
  const [newSummary, setNewSummary] = useState('')
  const [newParentId, setNewParentId] = useState('')

  const [editTitle, setEditTitle] = useState('')
  const [editSummary, setEditSummary] = useState('')
  const [editStatus, setEditStatus] = useState('proposed')
  const [deleteCascade, setDeleteCascade] = useState(false)
  const [childKind, setChildKind] = useState('work')
  const [childTitle, setChildTitle] = useState('')
  const [siblingKind, setSiblingKind] = useState('work')
  const [siblingTitle, setSiblingTitle] = useState('')

  const [edgeType, setEdgeType] = useState('references')
  const [edgeSourceId, setEdgeSourceId] = useState('')
  const [edgeTargetId, setEdgeTargetId] = useState('')
  const [selectedEdgeType, setSelectedEdgeType] = useState('references')

  useEffect(() => {
    setEditTitle(selectedSession?.title || '')
    setEditSummary(selectedSession?.summary || '')
    setEditStatus(selectedSession?.status || 'proposed')
    setChildTitle(selectedSession ? `Child of ${selectedSession.title}` : '')
    setSiblingTitle(selectedSession ? `Sibling of ${selectedSession.title}` : '')
  }, [selectedSession?.id, selectedSession?.title, selectedSession?.summary, selectedSession?.status])

  useEffect(() => {
    setSelectedEdgeType(selectedEdge?.type || 'references')
  }, [selectedEdge?.id, selectedEdge?.type])

  async function run(action: () => Promise<void>, success: string) {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await action()
      setNotice(success)
      onRefresh()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  function createSession() {
    return run(async () => {
      const response = await apiFetch<{ session: SessionView }>('/api/session-graph/sessions', {
        method: 'POST',
        body: JSON.stringify({
          kind: newKind,
          title: newTitle.trim(),
          summary: newSummary.trim(),
          parent_id: newParentId || null,
          metadata: { source: 'session-graph-crud-ui' },
        }),
      })
      setNewTitle('')
      setNewSummary('')
      setNewParentId('')
      onSelectSession(response.session.id)
    }, 'Session created.')
  }

  function duplicateSession() {
    if (!selectedSession) return
    return run(async () => {
      const response = await apiFetch<{ session: SessionView }>('/api/session-graph/sessions', {
        method: 'POST',
        body: JSON.stringify({
          kind: selectedSession.kind,
          title: `${selectedSession.title} copy`,
          summary: selectedSession.summary || `Copy of ${selectedSession.title}.`,
          parent_id: selectedSession.parent_id || null,
          facets: selectedSession.facets || {},
          policy: selectedSession.policy,
          state: selectedSession.state || {},
          metadata: {
            ...(selectedSession.metadata || {}),
            source: 'session-graph-duplicate-action',
            duplicated_from_session_id: selectedSession.id,
          },
        }),
      })
      onSelectSession(response.session.id)
    }, 'Session duplicated.')
  }

  function createChildSession() {
    if (!selectedSession) return
    return run(async () => {
      const response = await apiFetch<{ session: SessionView }>('/api/session-graph/sessions', {
        method: 'POST',
        body: JSON.stringify({
          kind: childKind,
          title: childTitle.trim() || `Child of ${selectedSession.title}`,
          summary: `Child session of ${selectedSession.title}.`,
          parent_id: selectedSession.id,
          root_id: selectedSession.root_id || selectedSession.id,
          metadata: {
            source: 'session-graph-create-child-action',
            parent_session_title: selectedSession.title,
          },
        }),
      })
      onSelectSession(response.session.id)
    }, 'Child session created.')
  }

  function createSiblingSession() {
    if (!selectedSession) return
    return run(async () => {
      const response = await apiFetch<{ session: SessionView }>('/api/session-graph/sessions', {
        method: 'POST',
        body: JSON.stringify({
          kind: siblingKind,
          title: siblingTitle.trim() || `Sibling of ${selectedSession.title}`,
          summary: `Sibling session of ${selectedSession.title}.`,
          parent_id: selectedSession.parent_id || null,
          root_id: selectedSession.root_id || selectedSession.id,
          metadata: {
            source: 'session-graph-create-sibling-action',
            sibling_of_session_id: selectedSession.id,
            sibling_of_session_title: selectedSession.title,
          },
        }),
      })
      onSelectSession(response.session.id)
    }, 'Sibling session created.')
  }

  function updateSession() {
    if (!selectedSession) return
    return run(async () => {
      await apiFetch(`/api/session-graph/sessions/${selectedSession.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ title: editTitle.trim(), summary: editSummary.trim(), status: editStatus, reason: 'Edited in session graph CRUD panel.' }),
      })
    }, 'Session updated.')
  }

  function deleteSession() {
    if (!selectedSession) return
    return run(async () => {
      await apiFetch(`/api/session-graph/sessions/${selectedSession.id}?cascade=${deleteCascade ? 'true' : 'false'}`, { method: 'DELETE' })
    }, 'Session deleted.')
  }

  function createEdge() {
    return run(async () => {
      await apiFetch('/api/session-graph/edges', {
        method: 'POST',
        body: JSON.stringify({ type: edgeType, source_session_id: edgeSourceId, target_session_id: edgeTargetId, metadata: { source: 'session-graph-crud-ui' } }),
      })
      setEdgeSourceId('')
      setEdgeTargetId('')
    }, 'Edge created.')
  }

  function updateEdge() {
    if (!selectedEdge) return
    return run(async () => {
      await apiFetch(`/api/session-graph/edges/${selectedEdge.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ type: selectedEdgeType, reason: 'Edited in session graph CRUD panel.' }),
      })
    }, 'Edge updated.')
  }

  function deleteEdge() {
    if (!selectedEdge) return
    return run(async () => {
      await apiFetch(`/api/session-graph/edges/${selectedEdge.id}`, { method: 'DELETE' })
    }, 'Edge deleted.')
  }

  return (
    <section className="sg-card sg-crud-card">
      <div className="sg-card-header sg-card-header-split">
        <div><Edit3 size={16} /><h3>Graph CRUD</h3></div>
        <span className="sg-count-pill">sessions + edges</span>
      </div>

      <p className="sg-muted sg-small">Create and edit graph topology directly. Use mounts for semantic repo projection; use raw edges for explicit graph relationships.</p>
      {error && <div className="sg-error sg-crud-message">{error}</div>}
      {notice && <div className="sg-crud-notice">{notice}</div>}

      <div className="sg-crud-grid">
        <div className="sg-crud-section">
          <h4><Plus size={14} /> Create session</h4>
          <label><span>Kind</span><select value={newKind} onChange={event => setNewKind(event.target.value)}>{sessionKinds.map(kind => <option key={kind} value={kind}>{kind}</option>)}</select></label>
          <label><span>Title</span><input value={newTitle} onChange={event => setNewTitle(event.target.value)} placeholder="Session title" /></label>
          <label><span>Summary</span><textarea value={newSummary} onChange={event => setNewSummary(event.target.value)} placeholder="What this session represents" /></label>
          <label><span>Parent</span><select value={newParentId} onChange={event => setNewParentId(event.target.value)}><option value="">No parent</option>{sessions.map(session => <option key={session.id} value={session.id}>{session.title} · {session.kind}</option>)}</select></label>
          <button className="sg-button sg-button-primary" type="button" disabled={busy || !newTitle.trim()} onClick={createSession}><Plus size={14} /> Create</button>
        </div>

        <div className="sg-crud-section">
          <h4><Edit3 size={14} /> Edit selected session</h4>
          {!selectedSession ? <p className="sg-muted sg-small">Select a session in the canvas first.</p> : <>
            <label><span>Title</span><input value={editTitle} onChange={event => setEditTitle(event.target.value)} /></label>
            <label><span>Summary</span><textarea value={editSummary} onChange={event => setEditSummary(event.target.value)} /></label>
            <label><span>Status</span><select value={editStatus} onChange={event => setEditStatus(event.target.value)}>{sessionStatuses.map(status => <option key={status} value={status}>{status}</option>)}</select></label>
            <div className="sg-form-actions"><button className="sg-button sg-button-primary" type="button" disabled={busy || !editTitle.trim()} onClick={updateSession}><RefreshCw size={14} /> Save</button><button className="sg-button" type="button" disabled={busy} onClick={duplicateSession}><Copy size={14} /> Duplicate</button></div>
            <div className="sg-child-action">
              <label><span>Child kind</span><select value={childKind} onChange={event => setChildKind(event.target.value)}>{sessionKinds.map(kind => <option key={kind} value={kind}>{kind}</option>)}</select></label>
              <label><span>Child title</span><input value={childTitle} onChange={event => setChildTitle(event.target.value)} placeholder="Child session title" /></label>
              <button className="sg-button" type="button" disabled={busy || !childTitle.trim()} onClick={createChildSession}><Plus size={14} /> Create child</button>
            </div>
            <div className="sg-child-action">
              <label><span>Sibling kind</span><select value={siblingKind} onChange={event => setSiblingKind(event.target.value)}>{sessionKinds.map(kind => <option key={kind} value={kind}>{kind}</option>)}</select></label>
              <label><span>Sibling title</span><input value={siblingTitle} onChange={event => setSiblingTitle(event.target.value)} placeholder="Sibling session title" /></label>
              <button className="sg-button" type="button" disabled={busy || !siblingTitle.trim()} onClick={createSiblingSession}><Plus size={14} /> Create sibling</button>
            </div>
            <label className="sg-crud-check"><input type="checkbox" checked={deleteCascade} onChange={event => setDeleteCascade(event.target.checked)} /> Cascade related edges/projections</label>
            <button className="sg-button sg-button-danger" type="button" disabled={busy} onClick={deleteSession}><Trash2 size={14} /> Delete session</button>
          </>}
        </div>

        <div className="sg-crud-section">
          <h4><GitBranch size={14} /> Create edge</h4>
          <label><span>Type</span><select value={edgeType} onChange={event => setEdgeType(event.target.value)}>{edgeTypes.map(type => <option key={type} value={type}>{type}</option>)}</select></label>
          <label><span>Source</span><select value={edgeSourceId} onChange={event => setEdgeSourceId(event.target.value)}><option value="">Select source</option>{sessions.map(session => <option key={session.id} value={session.id}>{session.title} · {session.kind}</option>)}</select></label>
          <label><span>Target</span><select value={edgeTargetId} onChange={event => setEdgeTargetId(event.target.value)}><option value="">Select target</option>{sessions.map(session => <option key={session.id} value={session.id}>{session.title} · {session.kind}</option>)}</select></label>
          <button className="sg-button sg-button-primary" type="button" disabled={busy || !edgeSourceId || !edgeTargetId || edgeSourceId === edgeTargetId} onClick={createEdge}><Plus size={14} /> Create edge</button>
        </div>

        <div className="sg-crud-section">
          <h4><Edit3 size={14} /> Edit selected edge</h4>
          {!selectedEdge ? <p className="sg-muted sg-small">Select an edge in the relationship strip or mounted sources panel first.</p> : <>
            <p className="sg-muted sg-small">{selectedEdge.source_session_id} → {selectedEdge.target_session_id}</p>
            <label><span>Type</span><select value={selectedEdgeType} onChange={event => setSelectedEdgeType(event.target.value)}>{edgeTypes.map(type => <option key={type} value={type}>{type}</option>)}</select></label>
            <div className="sg-form-actions"><button className="sg-button sg-button-primary" type="button" disabled={busy} onClick={updateEdge}><RefreshCw size={14} /> Save edge</button><button className="sg-button sg-button-danger" type="button" disabled={busy} onClick={deleteEdge}><Trash2 size={14} /> Delete edge</button></div>
          </>}
        </div>
      </div>
    </section>
  )
}
