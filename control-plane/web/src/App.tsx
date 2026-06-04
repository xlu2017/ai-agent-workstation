import { useState, useEffect, useCallback, useRef } from 'react'

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

interface ChatMsg {
  role: string
  content: string
  timestamp: string
  context_attached?: string[]
  staleness?: string
  status?: string
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

const SessionChat = ({ sessionId }: { sessionId: string }) => {
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetch(`${API}/sessions/${sessionId}/messages`)
      .then(response => response.json())
      .then(data => setMessages(data.messages || []))
      .catch(() => {})
  }, [sessionId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = () => {
    if (!input.trim() || sending) return
    setSending(true)
    const instruction = input.trim()
    setInput('')
    setMessages(previous => [...previous, { role: 'user', content: instruction, timestamp: new Date().toISOString() }])

    fetch(`${API}/sessions/${sessionId}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ instruction }),
    })
      .then(response => response.json())
      .then(data => {
        setMessages(previous => [...previous, {
          role: 'assistant',
          content: data.message || 'Task submitted.',
          timestamp: new Date().toISOString(),
          status: data.status,
          context_attached: data.context_attached,
          staleness: data.staleness,
        }])
      })
      .catch(error => {
        setMessages(previous => [...previous, {
          role: 'assistant',
          content: `Error: ${error.message}`,
          timestamp: new Date().toISOString(),
          status: 'error',
        }])
      })
      .finally(() => setSending(false))
  }

  return (
    <div className="chat-container">
      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-hint">Type an instruction. Ambient context (UI/editor/terminal) will be attached automatically.</div>
        )}
        {messages.map((message, index) => (
          <div key={index} className={`chat-msg chat-msg-${message.role}`}>
            <div className="chat-msg-header">
              <span className="chat-msg-role">{message.role === 'user' ? 'You' : 'Agent'}</span>
              <span className="chat-msg-time">{(message.timestamp || '').slice(11, 19)}</span>
            </div>
            <div className="chat-msg-content">{message.content}</div>
            {message.context_attached && message.context_attached.length > 0 && (
              <div className="chat-msg-meta">
                context: {message.context_attached.join(', ')}
                {message.staleness && message.staleness !== 'fresh' && (
                  <span className="badge badge-yellow" style={{ marginLeft: 6 }}>{message.staleness}</span>
                )}
              </div>
            )}
            {message.status && message.role === 'assistant' && (
              <div className="chat-msg-meta">
                status: <span className={`badge ${message.status === 'running' ? 'badge-blue' : message.status === 'completed' ? 'badge-green' : 'badge-yellow'}`}>{message.status}</span>
              </div>
            )}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>
      <div className="chat-input-row">
        <input
          className="chat-input"
          value={input}
          onChange={event => setInput(event.target.value)}
          onKeyDown={event => event.key === 'Enter' && sendMessage()}
          placeholder="Type instruction... (e.g. 'fix this', 'add tests', 'refactor')"
          disabled={sending}
        />
        <button className="btn btn-primary" onClick={sendMessage} disabled={sending || !input.trim()}>
          {sending ? '...' : 'Send'}
        </button>
      </div>
    </div>
  )
}

function SessionsPage() {
  const { data, refetch } = useFetch<{ sessions: Session[] }>(`${API}/sessions`)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [chatOpen, setChatOpen] = useState<string | null>(null)
  const [context, setContext] = useState<Record<string, any>>({})

  const loadContext = (id: string) => {
    if (expanded === id) { setExpanded(null); return }
    setExpanded(id)
    fetch(`${API}/sessions/${id}/context`).then(response => response.json()).then(data => setContext(previous => ({ ...previous, [id]: data })))
  }

  const destroySession = (id: string) => {
    if (confirm(`Destroy session ${id}?`)) {
      fetch(`${API}/sessions/${id}`, { method: 'DELETE' }).then(() => refetch())
    }
  }

  return (
    <div>
      <h2>Sessions</h2>
      {data?.sessions.map(session => (
        <div key={session.id} className="card">
          <div className="card-header">
            <span className="card-title">{session.id}</span>
            <span className={`badge ${session.status === 'active' ? 'badge-green' : 'badge-yellow'}`}>{session.status}</span>
          </div>
          <div className="meta">
            <span>branch: {session.branch || '-'}</span>
            <span>ports: {session.port_range || '-'}</span>
            <span>profile: {session.browser_profile || '-'}</span>
          </div>
          {session.task && <div className="meta" style={{ marginTop: 4 }}>task: {session.task}</div>}
          <div className="meta" style={{ marginTop: 6 }}>
            {session.has_ui_context && <span className="badge badge-blue">UI</span>}
            {session.has_editor_context && <span className="badge badge-blue">Editor</span>}
            {session.has_terminal_context && <span className="badge badge-blue">Terminal</span>}
          </div>
          <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
            <button className="btn btn-primary" onClick={() => setChatOpen(chatOpen === session.id ? null : session.id)}>
              {chatOpen === session.id ? 'Close Chat' : 'Chat'}
            </button>
            <button className="btn" onClick={() => loadContext(session.id)}>
              {expanded === session.id ? 'Hide Context' : 'Context'}
            </button>
            <button className="btn btn-danger" onClick={() => destroySession(session.id)}>Destroy</button>
          </div>
          {chatOpen === session.id && <SessionChat sessionId={session.id} />}
          {expanded === session.id && context[session.id] && (
            <div style={{ marginTop: 12 }}>
              {Object.entries(context[session.id].context || {}).map(([key, value]) => value && (
                <div key={key}>
                  <div className="meta" style={{ marginBottom: 4 }}>{key}:</div>
                  <div className="context-preview">{String(value).slice(0, 500)}</div>
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

function TimelinePage() {
  const { data: sessions } = useFetch<{ sessions: Session[] }>(`${API}/sessions`)
  const [selected, setSelected] = useState('')
  const [timeline, setTimeline] = useState<any>(null)

  useEffect(() => {
    if (selected) {
      fetch(`${API}/sessions/${selected}/timeline`).then(r => r.json()).then(setTimeline)
    }
  }, [selected])

  return (
    <div>
      <h2>Timeline</h2>
      <select className="btn" style={{ marginBottom: 16 }} value={selected} onChange={e => setSelected(e.target.value)}>
        <option value="">Select session...</option>
        {sessions?.sessions.map(s => <option key={s.id} value={s.id}>{s.id}</option>)}
      </select>
      {timeline?.summary && (
        <div className="grid">
          <div className="card stat">
            <div className="stat-value">${timeline.summary.cost_usd?.toFixed(4) || '0.00'}</div>
            <div className="stat-label">Cost</div>
          </div>
          <div className="card stat">
            <div className="stat-value">{timeline.summary.files_edited || 0}</div>
            <div className="stat-label">Files Edited</div>
          </div>
          <div className="card stat">
            <div className="stat-value">{timeline.summary.commands_run || 0}</div>
            <div className="stat-label">Commands</div>
          </div>
          <div className="card stat">
            <div className="stat-value">{timeline.summary.tests_passed || 0}/{(timeline.summary.tests_passed || 0) + (timeline.summary.tests_failed || 0)}</div>
            <div className="stat-label">Tests Pass</div>
          </div>
        </div>
      )}
      {timeline?.events?.length > 0 && (
        <div className="card" style={{ marginTop: 12 }}>
          <div className="card-title" style={{ marginBottom: 12 }}>Events</div>
          <div className="log-output">
            {timeline.events.map((ev: any, i: number) => {
              const ts = (ev.timestamp || '').slice(11, 19)
              const icon = ev.type === 'error' ? '✗' : ev.type === 'test_result' ? (ev.passed ? '✓' : '✗') : '·'
              return <div key={i} style={{ color: ev.type === 'error' || (ev.type === 'test_result' && !ev.passed) ? 'var(--red)' : 'inherit' }}>
                {ts} {icon} <strong>{ev.type}</strong> {ev.file || ev.command?.slice(0, 50) || ev.test || ev.model || ev.summary || ''}
              </div>
            })}
          </div>
        </div>
      )}
      {timeline && !timeline.events?.length && <div className="card"><p className="meta">No events recorded yet</p></div>}
    </div>
  )
}

function PostmortemPage() {
  const { data: proposed } = useFetch<{ triggers: any[] }>(`${API}/knowledge/proposed`, 10000)
  const { data: sessions } = useFetch<{ sessions: Session[] }>(`${API}/sessions`)
  const [selected, setSelected] = useState('')
  const [result, setResult] = useState<any>(null)

  const generate = () => {
    if (selected) {
      fetch(`${API}/sessions/${selected}/postmortem`, { method: 'POST' })
        .then(r => r.json()).then(setResult)
    }
  }

  const approve = (id: string) => {
    fetch(`${API}/knowledge/approve/${id}`, { method: 'POST' })
      .then(r => r.json()).then(() => alert('Trigger approved!'))
  }

  return (
    <div>
      <h2>Postmortems & Learning</h2>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <select className="btn" value={selected} onChange={e => setSelected(e.target.value)}>
          <option value="">Select session...</option>
          {sessions?.sessions.map(s => <option key={s.id} value={s.id}>{s.id}</option>)}
        </select>
        <button className="btn" onClick={generate} disabled={!selected}>Generate Postmortem</button>
      </div>

      {result && (
        <div className="card">
          <div className="card-title" style={{ marginBottom: 8 }}>Postmortem: {result.session_id}</div>
          <p><strong>Outcome:</strong> {result.outcome}</p>
          <p><strong>Reason:</strong> {result.failure_reason}</p>
          {result.root_causes?.map((c: string, i: number) => <p key={i} className="meta">Root cause: {c}</p>)}
          {result.proposed_triggers?.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <strong>Proposed Knowledge Triggers:</strong>
              {result.proposed_triggers.map((t: any) => (
                <div key={t.id} style={{ marginTop: 8, padding: 8, border: '1px solid var(--border)' }}>
                  <p>{t.description}</p>
                  <p className="meta">{t.content}</p>
                  <button className="btn" onClick={() => approve(t.id)} style={{ marginTop: 4 }}>Approve</button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {proposed?.triggers?.length ? (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="card-title" style={{ marginBottom: 12 }}>Pending Triggers ({proposed.triggers.length})</div>
          {proposed.triggers.map((t: any, i: number) => (
            <div key={i} style={{ marginBottom: 8, padding: 8, border: '1px solid var(--border)' }}>
              <p><strong>{t.id}</strong></p>
              <p className="meta">{t.description}</p>
              <button className="btn" onClick={() => approve(t.id)}>Approve</button>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}

const PAGES: Record<string, () => JSX.Element> = {
  Sessions: SessionsPage,
  Context: ContextPage,
  Timeline: TimelinePage,
  Postmortem: PostmortemPage,
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
