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

function CreateSessionForm({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [repo, setRepo] = useState('')
  const [branch, setBranch] = useState('')
  const [task, setTask] = useState('')
  const [creating, setCreating] = useState(false)

  const create = () => {
    setCreating(true)
    fetch(`${API}/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: name || undefined,
        repo: repo || undefined,
        branch: branch || undefined,
        task: task || undefined,
      }),
    })
      .then(response => response.json())
      .then(() => { setOpen(false); setName(''); setRepo(''); setBranch(''); setTask(''); onCreated() })
      .finally(() => setCreating(false))
  }

  if (!open) return <button className="btn btn-primary" onClick={() => setOpen(true)} style={{ marginBottom: 16 }}>+ Create Session</button>

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="card-title" style={{ marginBottom: 12 }}>New Session</div>
      <div style={{ display: 'grid', gap: 8 }}>
        <input className="chat-input" placeholder="Session name (auto-generated if empty)" value={name} onChange={e => setName(e.target.value)} />
        <input className="chat-input" placeholder="Repo path (e.g. /opt/workstation/repos/my-app)" value={repo} onChange={e => setRepo(e.target.value)} />
        <input className="chat-input" placeholder="Branch name (auto-generated if empty)" value={branch} onChange={e => setBranch(e.target.value)} />
        <input className="chat-input" placeholder="Task description (what the agent should do)" value={task} onChange={e => setTask(e.target.value)} />
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-primary" onClick={create} disabled={creating}>{creating ? 'Creating...' : 'Create'}</button>
          <button className="btn" onClick={() => setOpen(false)}>Cancel</button>
        </div>
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
      <CreateSessionForm onCreated={refetch} />
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
          <div style={{ marginTop: 8, display: 'flex', gap: 8, alignItems: 'center' }}>
            <button className="btn btn-primary" onClick={() => setChatOpen(chatOpen === session.id ? null : session.id)}>
              {chatOpen === session.id ? 'Close Chat' : 'Chat'}
            </button>
            <button className="btn" onClick={() => loadContext(session.id)}>
              {expanded === session.id ? 'Hide Context' : 'Context'}
            </button>
            <button className="btn btn-detach" onClick={() => window.open(`/#/session/${session.id}`, `session-${session.id}`, 'width=700,height=800,menubar=no,toolbar=no')}>
              Detach
            </button>
            <ModeSelector sessionId={session.id} />
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

function ToolCallEvent({ event }: { event: any }) {
  const tool = event.tool || ''
  const args = event.args || {}
  const success = event.success

  const getIcon = () => {
    if (tool === 'read_file') return 'R'
    if (tool === 'write_file' || tool === 'apply_patch') return 'W'
    if (tool === 'run_command') return '$'
    if (tool === 'git_commit') return 'G'
    if (tool === 'git_status' || tool === 'git_diff') return 'D'
    if (tool === 'list_files' || tool === 'grep') return '?'
    if (tool === 'run_validation') return 'T'
    if (tool === 'task_complete') return '*'
    if (tool === 'get_latest_context') return 'C'
    return '>'
  }

  const getDetail = () => {
    if (args.path) return args.path
    if (args.command) return args.command.slice(0, 60)
    if (args.message) return args.message.slice(0, 60)
    if (args.pattern) return `/${args.pattern}/`
    if (args.summary) return args.summary.slice(0, 60)
    return ''
  }

  return (
    <div className={`timeline-event ${success ? '' : 'timeline-event-failed'}`}>
      <span className="timeline-icon">{getIcon()}</span>
      <span className="timeline-tool">{tool}</span>
      <span className="timeline-detail">{getDetail()}</span>
      <span className={`timeline-status ${success ? 'timeline-ok' : 'timeline-fail'}`}>
        {success ? '✓' : '✗'}
      </span>
    </div>
  )
}

function TimelinePage() {
  const { data: sessions } = useFetch<{ sessions: Session[] }>(`${API}/sessions`)
  const [selected, setSelected] = useState('')
  const [timeline, setTimeline] = useState<any>(null)

  useEffect(() => {
    if (selected) {
      const load = () => fetch(`${API}/sessions/${selected}/timeline`).then(r => r.json()).then(setTimeline)
      load()
      const interval = setInterval(load, 3000)
      return () => clearInterval(interval)
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
            <div className="stat-value">{timeline.summary.tool_calls || 0}</div>
            <div className="stat-label">Tool Calls</div>
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
            <div className="stat-value">{timeline.summary.commits || 0}</div>
            <div className="stat-label">Commits</div>
          </div>
        </div>
      )}
      {timeline?.events?.length > 0 && (
        <div className="card" style={{ marginTop: 12 }}>
          <div className="card-title" style={{ marginBottom: 12 }}>Events ({timeline.events.length})</div>
          <div className="timeline-list">
            {timeline.events.map((ev: any, i: number) => {
              const ts = (ev.timestamp || '').slice(11, 19)
              if (ev.type === 'tool_call') {
                return <div key={i} className="timeline-row">
                  <span className="timeline-ts">{ts}</span>
                  <ToolCallEvent event={ev} />
                </div>
              }
              if (ev.type === 'task_start') {
                return <div key={i} className="timeline-row timeline-task-start">
                  <span className="timeline-ts">{ts}</span>
                  <span className="timeline-icon">&gt;</span>
                  <strong>TASK START</strong>
                  <span className="timeline-detail">{ev.executor} — {(ev.instruction || '').slice(0, 60)}</span>
                </div>
              }
              if (ev.type === 'task_complete') {
                const statusColor = ev.status === 'committed' ? 'badge-green' : ev.status === 'failed' ? 'badge-red' : 'badge-yellow'
                return <div key={i} className="timeline-row timeline-task-done">
                  <span className="timeline-ts">{ts}</span>
                  <span className="timeline-icon">*</span>
                  <strong>TASK DONE</strong>
                  <span className={`badge ${statusColor}`}>{ev.status}</span>
                  {ev.commit && <code className="timeline-sha">{String(ev.commit).slice(0, 8)}</code>}
                  {ev.tool_calls && <span className="meta">({ev.tool_calls} tool calls)</span>}
                </div>
              }
              if (ev.type === 'agent_message') {
                return <div key={i} className="timeline-row">
                  <span className="timeline-ts">{ts}</span>
                  <span className="timeline-icon">#</span>
                  <span className="timeline-detail">{(ev.text || '').slice(0, 80)}</span>
                </div>
              }
              return <div key={i} className="timeline-row">
                <span className="timeline-ts">{ts}</span>
                <span className="timeline-icon">.</span>
                <strong>{ev.type}</strong>
                <span className="timeline-detail">{ev.file || ev.command?.slice(0, 50) || ev.instruction?.slice(0, 50) || ''}</span>
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

const ModeSelector = ({ sessionId }: { sessionId: string }) => {
  const [mode, setMode] = useState('safe')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${API}/sessions/${sessionId}/mode`)
      .then(response => response.json())
      .then(data => { setMode(data.mode || 'safe'); setLoading(false) })
      .catch(() => setLoading(false))
  }, [sessionId])

  const changeMode = (newMode: string) => {
    setMode(newMode)
    fetch(`${API}/sessions/${sessionId}/mode`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: newMode }),
    })
  }

  if (loading) return null

  return (
    <select
      className="mode-selector"
      value={mode}
      onChange={event => changeMode(event.target.value)}
    >
      <option value="safe">Safe</option>
      <option value="review-required">Review Required</option>
      <option value="full-autonomy-branch">Full Autonomy Branch</option>
      <option value="fork-and-prove">Fork-and-Prove</option>
    </select>
  )
}

interface ForkCandidate {
  candidate_id: string
  title: string
  interpretation: string
  planned_changes: string[]
  validation_plan: string[]
  risk_level: string
  score: number
  score_breakdown: Record<string, number>
  selected_for_implementation: boolean
  review_status?: string
}

function ForkAndProvePage() {
  const { data: sessionsData } = useFetch<{ sessions: Session[] }>(`${API}/sessions`)
  const [selectedSession, setSelectedSession] = useState('')
  const [candidates, setCandidates] = useState<ForkCandidate[]>([])
  const [comparison, setComparison] = useState('')
  const [instruction, setInstruction] = useState('')
  const [running, setRunning] = useState(false)

  useEffect(() => {
    if (!selectedSession) return
    fetch(`${API}/sessions/${selectedSession}/fork-and-prove/candidates`)
      .then(response => response.json())
      .then(data => setCandidates(data.candidates || []))
      .catch(() => {})
    fetch(`${API}/sessions/${selectedSession}/fork-and-prove/comparison`)
      .then(response => response.json())
      .then(data => setComparison(data.report || ''))
      .catch(() => setComparison(''))
  }, [selectedSession])

  const startFork = () => {
    if (!selectedSession || !instruction.trim()) return
    setRunning(true)
    fetch(`${API}/sessions/${selectedSession}/fork-and-prove`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ instruction }),
    })
      .then(response => response.json())
      .then(() => {
        fetch(`${API}/sessions/${selectedSession}/fork-and-prove/candidates`)
          .then(response => response.json())
          .then(data => setCandidates(data.candidates || []))
        fetch(`${API}/sessions/${selectedSession}/fork-and-prove/comparison`)
          .then(response => response.json())
          .then(data => setComparison(data.report || ''))
      })
      .finally(() => setRunning(false))
  }

  const actionCandidate = (candidateId: string, action: string) => {
    fetch(`${API}/sessions/${selectedSession}/fork-and-prove/${candidateId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action }),
    }).then(() => {
      fetch(`${API}/sessions/${selectedSession}/fork-and-prove/candidates`)
        .then(response => response.json())
        .then(data => setCandidates(data.candidates || []))
    })
  }

  return (
    <div>
      <h2>Fork-and-Prove</h2>
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-title" style={{ marginBottom: 8 }}>Run Fork-and-Prove</div>
        <select
          className="mode-selector"
          style={{ width: '100%', marginBottom: 8 }}
          value={selectedSession}
          onChange={event => setSelectedSession(event.target.value)}
        >
          <option value="">Select session...</option>
          {sessionsData?.sessions.map(session => (
            <option key={session.id} value={session.id}>{session.id} ({session.branch})</option>
          ))}
        </select>
        <input
          className="chat-input"
          placeholder="Ambiguous task instruction..."
          value={instruction}
          onChange={event => setInstruction(event.target.value)}
          onKeyDown={event => event.key === 'Enter' && startFork()}
          disabled={running}
          style={{ marginBottom: 8 }}
        />
        <button className="btn btn-primary" onClick={startFork} disabled={running || !selectedSession || !instruction.trim()}>
          {running ? 'Running...' : 'Start Fork-and-Prove'}
        </button>
      </div>

      {candidates.length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-title" style={{ marginBottom: 12 }}>Candidates ({candidates.length})</div>
          {candidates.map(candidate => (
            <div key={candidate.candidate_id} className="fork-candidate">
              <div className="fork-candidate-header">
                <strong>{candidate.candidate_id}: {candidate.title}</strong>
                <span className="fork-score">Score: {candidate.score.toFixed(3)}</span>
                {candidate.selected_for_implementation && <span className="badge badge-green">SELECTED</span>}
                {candidate.review_status === 'approved' && <span className="badge badge-green">Approved</span>}
                {candidate.review_status === 'rejected' && <span className="badge badge-red">Rejected</span>}
              </div>
              <div className="meta">{candidate.interpretation}</div>
              <div className="meta" style={{ marginTop: 4 }}>
                Risk: <span className={`badge ${candidate.risk_level === 'low' ? 'badge-green' : candidate.risk_level === 'high' ? 'badge-red' : 'badge-yellow'}`}>{candidate.risk_level}</span>
              </div>
              {candidate.score_breakdown && (
                <div className="fork-scores">
                  {Object.entries(candidate.score_breakdown).map(([dimension, value]) => (
                    <span key={dimension} className="fork-score-dim">{dimension}: {Number(value).toFixed(2)}</span>
                  ))}
                </div>
              )}
              {candidate.planned_changes && (
                <div className="meta" style={{ marginTop: 4 }}>
                  Changes: {candidate.planned_changes.join(', ')}
                </div>
              )}
              {candidate.selected_for_implementation && !candidate.review_status && (
                <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
                  <button className="btn btn-primary" onClick={() => actionCandidate(candidate.candidate_id, 'approved')}>Approve</button>
                  <button className="btn btn-danger" onClick={() => actionCandidate(candidate.candidate_id, 'rejected')}>Reject</button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {comparison && (
        <div className="card">
          <div className="card-title" style={{ marginBottom: 12 }}>Comparison Report</div>
          <pre className="log-output" style={{ whiteSpace: 'pre-wrap', maxHeight: 400 }}>{comparison}</pre>
        </div>
      )}
    </div>
  )
}

// --- Benchmark Page ---

interface BenchTask {
  id: string
  repo: string
  title: string
  difficulty: string
  category: string
  context_source: string
}

interface BenchRun {
  run_id: string
  total_tasks?: number
  passed?: number
  failed?: number
  needs_review?: number
  total_runtime?: number
  total_cost?: number
}

function BenchmarkPage() {
  const { data: tasksData, loading: tasksLoading } = useFetch<{ tasks: BenchTask[] }>(`${API}/benchmark/tasks`, 10000)
  const { data: resultsData, loading: resultsLoading, refetch: refetchResults } = useFetch<{ runs: BenchRun[] }>(`${API}/benchmark/results`, 10000)
  const [running, setRunning] = useState(false)

  const runTask = (repo: string, taskId: string) => {
    setRunning(true)
    fetch(`${API}/benchmark/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo, task_id: taskId }),
    })
      .then(() => { setTimeout(refetchResults, 3000) })
      .finally(() => setRunning(false))
  }

  const runSuite = (repo: string) => {
    setRunning(true)
    fetch(`${API}/benchmark/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo }),
    })
      .then(() => { setTimeout(refetchResults, 5000) })
      .finally(() => setRunning(false))
  }

  return (
    <div>
      <h2>Benchmark</h2>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-title">Available Tasks</div>
        {tasksLoading && <div>Loading...</div>}
        {tasksData?.tasks && tasksData.tasks.length === 0 && <div className="meta">No tasks found. Deploy bench-tasks to /opt/workstation/bench-tasks/</div>}
        {tasksData?.tasks && tasksData.tasks.length > 0 && (
          <table style={{ width: '100%', fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: 'left' }}>
                <th>ID</th><th>Category</th><th>Difficulty</th><th>Context</th><th>Action</th>
              </tr>
            </thead>
            <tbody>
              {tasksData.tasks.map(t => (
                <tr key={t.id}>
                  <td>{t.id}</td>
                  <td><span className="badge">{t.category}</span></td>
                  <td>{t.difficulty}</td>
                  <td>{t.context_source}</td>
                  <td>
                    <button className="btn" disabled={running} onClick={() => runTask(t.repo, t.id)} style={{ fontSize: 11 }}>
                      Run
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {tasksData?.tasks && tasksData.tasks.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <button className="btn btn-primary" disabled={running} onClick={() => runSuite('cypress-realworld-app')}>
              {running ? 'Running...' : 'Run Full Suite'}
            </button>
          </div>
        )}
      </div>

      <div className="card">
        <div className="card-title">Results</div>
        {resultsLoading && <div>Loading...</div>}
        {resultsData?.runs && resultsData.runs.length === 0 && <div className="meta">No results yet. Run a benchmark task first.</div>}
        {resultsData?.runs && resultsData.runs.length > 0 && (
          <table style={{ width: '100%', fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: 'left' }}>
                <th>Run ID</th><th>Tasks</th><th>Passed</th><th>Failed</th><th>Review</th><th>Cost</th><th>Runtime</th>
              </tr>
            </thead>
            <tbody>
              {resultsData.runs.map(r => (
                <tr key={r.run_id}>
                  <td>{r.run_id}</td>
                  <td>{r.total_tasks ?? '?'}</td>
                  <td style={{ color: '#4ade80' }}>{r.passed ?? '-'}</td>
                  <td style={{ color: '#f87171' }}>{r.failed ?? '-'}</td>
                  <td style={{ color: '#fbbf24' }}>{r.needs_review ?? '-'}</td>
                  <td>${(r.total_cost ?? 0).toFixed(4)}</td>
                  <td>{(r.total_runtime ?? 0).toFixed(1)}s</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

const PAGES: Record<string, () => JSX.Element> = {
  Sessions: SessionsPage,
  Context: ContextPage,
  Timeline: TimelinePage,
  'Fork-Prove': ForkAndProvePage,
  Postmortem: PostmortemPage,
  Models: ModelsPage,
  Knowledge: KnowledgePage,
  Benchmark: BenchmarkPage,
  Health: HealthPage,
  Logs: LogsPage,
}

const DetachedSessionPage = ({ sessionId }: { sessionId: string }) => {
  const { data: session } = useFetch<Session>(`${API}/sessions/${sessionId}`, 5000)
  const [contextData, setContextData] = useState<any>(null)
  const [timeline, setTimeline] = useState<any>(null)

  useEffect(() => {
    fetch(`${API}/sessions/${sessionId}/context`).then(response => response.json()).then(setContextData)
    fetch(`${API}/sessions/${sessionId}/timeline`).then(response => response.json()).then(setTimeline)
    const interval = setInterval(() => {
      fetch(`${API}/sessions/${sessionId}/context`).then(response => response.json()).then(setContextData)
      fetch(`${API}/sessions/${sessionId}/timeline`).then(response => response.json()).then(setTimeline)
    }, 5000)
    return () => clearInterval(interval)
  }, [sessionId])

  if (!session) return <div className="detached-loading">Loading session...</div>

  return (
    <div className="detached-session">
      <div className="detached-header">
        <h2>{sessionId}</h2>
        <span className={`badge ${session.status === 'active' ? 'badge-green' : 'badge-yellow'}`}>{session.status}</span>
      </div>
      <div className="detached-meta">
        <span>branch: {session.branch || '-'}</span>
        <span>ports: {session.port_range || '-'}</span>
        <span>task: {session.task || '-'}</span>
      </div>
      {timeline?.summary && (
        <div className="detached-stats">
          <div className="stat-pill">Cost: ${timeline.summary.cost_usd?.toFixed(4) || '0.00'}</div>
          <div className="stat-pill">Files: {timeline.summary.files_edited || 0}</div>
          <div className="stat-pill">Commands: {timeline.summary.commands_run || 0}</div>
          <div className="stat-pill">Tests: {timeline.summary.tests_passed || 0}/{(timeline.summary.tests_passed || 0) + (timeline.summary.tests_failed || 0)}</div>
        </div>
      )}
      <div className="detached-context-badges">
        {contextData?.context?.ui && <span className="badge badge-blue">UI context attached</span>}
        {contextData?.context?.editor && <span className="badge badge-blue">Editor context attached</span>}
        {contextData?.context?.terminal && <span className="badge badge-blue">Terminal context attached</span>}
      </div>
      <SessionChat sessionId={sessionId} />
      {contextData?.context && (
        <div className="detached-context">
          <h3>Ambient Context</h3>
          {Object.entries(contextData.context).map(([key, value]) => value && (
            <details key={key} className="context-detail">
              <summary>{key}</summary>
              <div className="context-preview">{String(value).slice(0, 1000)}</div>
            </details>
          ))}
        </div>
      )}
      {timeline?.events?.length > 0 && (
        <div className="detached-timeline">
          <h3>Timeline</h3>
          <div className="log-output" style={{ maxHeight: '200px' }}>
            {timeline.events.slice(-20).map((event: any, index: number) => {
              const timestamp = (event.timestamp || '').slice(11, 19)
              return <div key={index}>{timestamp} <strong>{event.type}</strong> {event.file || event.command?.slice(0, 50) || event.instruction?.slice(0, 50) || ''}</div>
            })}
          </div>
        </div>
      )}
    </div>
  )
}

export function App() {
  const [page, setPage] = useState('Sessions')
  const [detachedSession, setDetachedSession] = useState<string | null>(null)

  useEffect(() => {
    const handleHash = () => {
      const hash = window.location.hash
      const sessionMatch = hash.match(/^#\/session\/(.+)$/)
      if (sessionMatch) {
        setDetachedSession(sessionMatch[1])
      } else {
        setDetachedSession(null)
      }
    }
    handleHash()
    window.addEventListener('hashchange', handleHash)
    return () => window.removeEventListener('hashchange', handleHash)
  }, [])

  if (detachedSession) {
    return <DetachedSessionPage sessionId={detachedSession} />
  }

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
