import { useState, useEffect, useCallback } from 'react'

interface Session {
  id: string
  branch: string
  port_range: string
  status: string
  task: string
  repo_path: string
  worktree_path: string
  browser_profile: string
  has_ui_context: boolean
  has_editor_context: boolean
  has_terminal_context: boolean
  created_at: string
  context?: { ui: string | null; editor: string | null; terminal: string | null }
}

interface Health {
  litellm: { status: string }
  openhands: { status: string }
  bridge: { status: string }
  disk: { used: string; available: string; percent: string }
  memory: { total: string; used: string; available: string }
  cpu: { load_1m: string; load_5m: string }
  docker: { name: string; status: string; ports: string }[]
  active_ports: number[]
}

interface KnowledgeEntry {
  id: string
  description: string
  confidence: string
  activation_paths: string[]
  activation_keywords: string[]
}

const API = '/api'

function useFetch<T>(url: string, interval = 5000) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)

  const refetch = useCallback(() => {
    fetch(url).then(r => r.json()).then(setData).catch(() => {}).finally(() => setLoading(false))
  }, [url])

  useEffect(() => {
    refetch()
    const id = setInterval(refetch, interval)
    return () => clearInterval(id)
  }, [refetch, interval])

  return { data, loading, refetch }
}

function SessionsPage() {
  const { data, refetch } = useFetch<{ sessions: Session[] }>(`${API}/sessions`)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [context, setContext] = useState<Record<string, any>>({})

  const loadContext = (id: string) => {
    if (expanded === id) { setExpanded(null); return }
    setExpanded(id)
    fetch(`${API}/sessions/${id}/context`).then(r => r.json()).then(d => setContext(prev => ({ ...prev, [id]: d })))
  }

  const destroySession = (id: string) => {
    if (confirm(`Destroy session ${id}?`)) {
      fetch(`${API}/sessions/${id}`, { method: 'DELETE' }).then(() => refetch())
    }
  }

  return (
    <div>
      <h2>Sessions</h2>
      {data?.sessions.map(s => (
        <div key={s.id} className="card">
          <div className="card-header">
            <span className="card-title">{s.id}</span>
            <span className={`badge ${s.status === 'active' ? 'badge-green' : 'badge-yellow'}`}>{s.status}</span>
          </div>
          <div className="meta">
            <span>branch: {s.branch || '-'}</span>
            <span>ports: {s.port_range || '-'}</span>
            <span>profile: {s.browser_profile || '-'}</span>
          </div>
          {s.task && <div className="meta" style={{ marginTop: 4 }}>task: {s.task}</div>}
          <div className="meta" style={{ marginTop: 6 }}>
            {s.has_ui_context && <span className="badge badge-blue">UI</span>}
            {s.has_editor_context && <span className="badge badge-blue">Editor</span>}
            {s.has_terminal_context && <span className="badge badge-blue">Terminal</span>}
          </div>
          <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
            <button className="btn" onClick={() => loadContext(s.id)}>
              {expanded === s.id ? 'Hide Context' : 'Show Context'}
            </button>
            <button className="btn btn-danger" onClick={() => destroySession(s.id)}>Destroy</button>
          </div>
          {expanded === s.id && context[s.id] && (
            <div style={{ marginTop: 12 }}>
              {Object.entries(context[s.id].context || {}).map(([k, v]) => v && (
                <div key={k}>
                  <div className="meta" style={{ marginBottom: 4 }}>{k}:</div>
                  <div className="context-preview">{String(v).slice(0, 500)}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
      {data?.sessions.length === 0 && <div className="card"><p className="meta">No active sessions</p></div>}
    </div>
  )
}

function ContextPage() {
  const { data } = useFetch<{ sessions: Session[] }>(`${API}/sessions`)
  const [selected, setSelected] = useState('')
  const [ctx, setCtx] = useState<any>(null)

  useEffect(() => {
    if (selected) fetch(`${API}/sessions/${selected}/context`).then(r => r.json()).then(setCtx)
  }, [selected])

  return (
    <div>
      <h2>Context</h2>
      <select className="btn" style={{ marginBottom: 16 }} value={selected} onChange={e => setSelected(e.target.value)}>
        <option value="">Select session...</option>
        {data?.sessions.map(s => <option key={s.id} value={s.id}>{s.id}</option>)}
      </select>
      {ctx && (
        <div>
          {['ui', 'editor', 'terminal'].map(type => (
            <div key={type} className="card">
              <div className="card-title" style={{ marginBottom: 8 }}>{type} context</div>
              {ctx.context[type]
                ? <div className="context-preview">{ctx.context[type]}</div>
                : <p className="meta">(none)</p>
              }
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function ModelsPage() {
  const { data } = useFetch<{ live: any[]; configured: any[] }>(`${API}/models`, 10000)

  return (
    <div>
      <h2>Models</h2>
      <div className="card">
        <div className="card-title" style={{ marginBottom: 12 }}>Configured Providers</div>
        <table>
          <thead><tr><th>Name</th><th>Model</th><th>Provider</th></tr></thead>
          <tbody>
            {data?.configured?.map((m, i) => (
              <tr key={i}>
                <td>{m.model_name}</td>
                <td>{m.litellm_params?.model}</td>
                <td>{m.litellm_params?.model?.split('/')[0]}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {(!data?.configured || data.configured.length === 0) && <p className="meta">No models configured</p>}
      </div>
    </div>
  )
}

function KnowledgePage() {
  const { data } = useFetch<{ entries: KnowledgeEntry[] }>(`${API}/knowledge`, 10000)

  return (
    <div>
      <h2>Knowledge</h2>
      {data?.entries?.map(e => (
        <div key={e.id} className="card">
          <div className="card-header">
            <span className="card-title">{e.id}</span>
            <span className={`badge ${e.confidence === 'high' ? 'badge-green' : 'badge-yellow'}`}>{e.confidence}</span>
          </div>
          <p className="meta">{e.description}</p>
          <div className="meta" style={{ marginTop: 4 }}>
            {e.activation_paths?.map((p, i) => <span key={i} className="badge badge-blue" style={{ marginRight: 4 }}>{p}</span>)}
            {e.activation_keywords?.map((k, i) => <span key={i} className="badge badge-yellow" style={{ marginRight: 4 }}>{k}</span>)}
          </div>
        </div>
      ))}
      {(!data?.entries || data.entries.length === 0) && <div className="card"><p className="meta">No knowledge entries</p></div>}
    </div>
  )
}

function HealthPage() {
  const { data } = useFetch<Health>(`${API}/health`, 3000)

  if (!data) return <div><h2>Health</h2><p className="meta">Loading...</p></div>

  return (
    <div>
      <h2>Health</h2>
      <div className="grid">
        <div className="card stat">
          <div className="stat-value">{data.cpu?.load_1m || '-'}</div>
          <div className="stat-label">CPU Load (1m)</div>
        </div>
        <div className="card stat">
          <div className="stat-value">{data.memory?.used || '-'}</div>
          <div className="stat-label">RAM Used / {data.memory?.total || '-'}</div>
        </div>
        <div className="card stat">
          <div className="stat-value">{data.disk?.percent || '-'}</div>
          <div className="stat-label">Disk ({data.disk?.available || '-'} free)</div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 12 }}>
        <div className="card-title" style={{ marginBottom: 12 }}>Services</div>
        {['litellm', 'openhands', 'bridge'].map(svc => {
          const s = (data as any)[svc] || {}
          return (
            <div key={svc} className="service-row">
              <div className={`dot ${s.status === 'healthy' ? 'dot-green' : 'dot-red'}`} />
              <span style={{ flex: 1 }}>{svc}</span>
              <span className={`badge ${s.status === 'healthy' ? 'badge-green' : 'badge-red'}`}>{s.status || 'unknown'}</span>
            </div>
          )
        })}
      </div>

      <div className="card" style={{ marginTop: 12 }}>
        <div className="card-title" style={{ marginBottom: 12 }}>Docker Containers</div>
        <table>
          <thead><tr><th>Name</th><th>Status</th><th>Ports</th></tr></thead>
          <tbody>
            {data.docker?.map((c, i) => (
              <tr key={i}><td>{c.name}</td><td>{c.status}</td><td>{c.ports}</td></tr>
            ))}
          </tbody>
        </table>
      </div>

      {data.active_ports?.length > 0 && (
        <div className="card" style={{ marginTop: 12 }}>
          <div className="card-title" style={{ marginBottom: 8 }}>Active Ports</div>
          <div className="meta">{data.active_ports.join(', ')}</div>
        </div>
      )}
    </div>
  )
}

function LogsPage() {
  const { data, refetch } = useFetch<{ litellm: string; bridge: string[] }>(`${API}/logs`, 10000)

  return (
    <div>
      <h2>Logs</h2>
      <button className="btn" onClick={refetch} style={{ marginBottom: 12 }}>Refresh</button>
      <div className="card">
        <div className="card-title" style={{ marginBottom: 8 }}>LiteLLM</div>
        <div className="log-output">{data?.litellm || '(no logs)'}</div>
      </div>
      <div className="card" style={{ marginTop: 12 }}>
        <div className="card-title" style={{ marginBottom: 8 }}>Bridge Events</div>
        <div className="log-output">{data?.bridge?.slice(-20).join('\n') || '(no events)'}</div>
      </div>
    </div>
  )
}

const PAGES: Record<string, () => JSX.Element> = {
  Sessions: SessionsPage,
  Context: ContextPage,
  Models: ModelsPage,
  Knowledge: KnowledgePage,
  Health: HealthPage,
  Logs: LogsPage,
}

export function App() {
  const [page, setPage] = useState('Sessions')
  const Page = PAGES[page]

  return (
    <div className="app">
      <aside className="sidebar">
        <h1>Control Plane</h1>
        <nav>
          {Object.keys(PAGES).map(p => (
            <a key={p} href="#" className={p === page ? 'active' : ''} onClick={e => { e.preventDefault(); setPage(p) }}>
              {p}
            </a>
          ))}
        </nav>
      </aside>
      <main className="main">
        <Page />
      </main>
    </div>
  )
}
