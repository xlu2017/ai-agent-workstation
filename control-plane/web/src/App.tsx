import { useState, useEffect, useRef, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import { Menu, Send, ChevronLeft, Folder, GitBranch, Plus, X, Circle, CheckCircle, AlertCircle, Clock, ArrowUp, Power, RefreshCw, Server, Monitor, Maximize2, Minimize2, Download } from 'lucide-react'

// crypto.randomUUID() requires a secure context (HTTPS or localhost).
// When accessed via HTTP + IP (e.g. http://<tailscale-ip>:5173/), it's unavailable.
function generateUUID(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = (Math.random() * 16) | 0
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
  })
}

interface TaskHandle {
  task_id: string
  session_id: string
  state: string
  message: string
  routing_decision: string
  plan_summary: string
  error: string
  events_path: string
  metadata: { files_edited?: string[]; executor?: string; duration_seconds?: number; commands_run?: string[]; tests_passed?: number; tests_failed?: number }
}

interface SessionEvent {
  event_type: string
  session_id: string
  data: Record<string, any>
  event_id: string
  timestamp: string
  sequence: number
}

interface SessionState {
  state: string
  last_event: string
  total_events: number
}

interface Health {
  agent_core: { status: string; error?: string }
  litellm: { status: string; url?: string; error?: string }
  openhands: { status: string; error?: string }
  bridge: { status: string; error?: string }
  disk: { used: string; available: string; percent: string }
  memory: { total: string; used: string; available: string }
  cpu: { load_1m: string; load_5m: string; load_15m: string }
  active_ports: number[]
}

interface RemoteDesktopConfig {
  enabled: boolean
  provider: string
  url: string
  rdp_host: string
  security: string
  auto_login: boolean
}

interface RemoteDesktopHealth {
  ok: boolean
  enabled: boolean
  provider: string
  guacamole: string
  guacd: string
  rdp: string
  rdp_host: string
  rdp_port: number
}

interface ChatEntry {
  id: string
  role: 'user' | 'system'
  content: string
  timestamp: string
  taskHandle?: TaskHandle
  events?: SessionEvent[]
  sessionState?: SessionState
}

const API = '/api'
const CONTROL_API = window.location.port === '5173'
  ? `${window.location.protocol}//${window.location.hostname}:9877/api`
  : API

interface GuacamoleSession {
  authToken: string
  username: string
  dataSource: string
  availableDataSources: string[]
  connection_url: string
}

function StatusDot({ status }: { status: string }) {
  const color = status === 'healthy' ? '#4ade80' : status === 'unhealthy' ? '#f87171' : '#fbbf24'
  return <Circle size={8} fill={color} stroke={color} style={{ marginRight: 6 }} />
}

function RemoteDesktopPage() {
  const [config, setConfig] = useState<RemoteDesktopConfig | null>(null)
  const [remoteHealth, setRemoteHealth] = useState<RemoteDesktopHealth | null>(null)
  const [error, setError] = useState('')
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [frameSrc, setFrameSrc] = useState('')
  const [autoLoginStatus, setAutoLoginStatus] = useState('')
  const frameShellRef = useRef<HTMLDivElement>(null)

  const refresh = useCallback(() => {
    fetch(`${API}/v2/remote-desktop/config`)
      .then(r => r.json())
      .then(setConfig)
      .catch(err => setError((err as Error).message))

    fetch(`${API}/v2/remote-desktop/health`)
      .then(r => r.json())
      .then(setRemoteHealth)
      .catch(() => {})
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 10000)
    return () => clearInterval(id)
  }, [refresh])

  useEffect(() => {
    const onFullscreenChange = () => {
      setIsFullscreen(document.fullscreenElement === frameShellRef.current)
    }
    document.addEventListener('fullscreenchange', onFullscreenChange)
    return () => document.removeEventListener('fullscreenchange', onFullscreenChange)
  }, [])

  const toggleFullscreen = useCallback(() => {
    const frameShell = frameShellRef.current
    if (!frameShell) return

    if (document.fullscreenElement) {
      document.exitFullscreen().catch(err => setError((err as Error).message))
      return
    }

    frameShell.requestFullscreen().catch(err => setError((err as Error).message))
  }, [])

  const startGuacamoleSession = useCallback(() => {
    if (!config?.enabled) return
    if (!config.auto_login) {
      setFrameSrc(config.url)
      setAutoLoginStatus('')
      return
    }

    setAutoLoginStatus('Signing in to Guacamole...')
    fetch(`${API}/v2/remote-desktop/token`, { method: 'POST' })
      .then(async response => {
        if (!response.ok) {
          const message = await response.text()
          throw new Error(message || 'Unable to sign in to Guacamole')
        }
        return response.json() as Promise<GuacamoleSession>
      })
      .then(session => {
        localStorage.setItem('GUAC_AUTH', JSON.stringify({
          authToken: session.authToken,
          username: session.username,
          dataSource: session.dataSource,
          availableDataSources: session.availableDataSources,
        }))
        setFrameSrc(session.connection_url || config.url)
        setAutoLoginStatus('Signed in')
      })
      .catch(err => {
        setAutoLoginStatus(`Auto-login failed: ${(err as Error).message}`)
        setFrameSrc(config.url)
      })
  }, [config?.auto_login, config?.enabled, config?.url])

  useEffect(() => {
    if (config?.enabled) {
      startGuacamoleSession()
    }
  }, [config?.auto_login, config?.enabled, config?.url, startGuacamoleSession])

  if (error) {
    return (
      <div className="remote-desktop-page">
        <div className="remote-card">
          <h2>Remote Desktop</h2>
          <p className="remote-error">Unable to load remote desktop config: {error}</p>
        </div>
      </div>
    )
  }

  if (!config) {
    return <div className="remote-desktop-page"><div className="remote-card">Loading remote desktop status...</div></div>
  }

  const guacamoleStatus = remoteHealth?.guacamole || 'unknown'
  const rdpStatus = remoteHealth?.rdp || 'unknown'
  const overallStatus = config.enabled ? (remoteHealth?.ok ? 'ready' : 'degraded') : 'disabled'

  return (
    <div className="remote-desktop-page">
      <div className="remote-header">
        <div>
          <h2>Remote Desktop</h2>
          <p>Browser access is proxied through Apache Guacamole to xRDP on the private network.</p>
        </div>
        <button className="btn-refresh" onClick={refresh}><RefreshCw size={14} /> Refresh</button>
      </div>

      <div className="remote-status-grid">
        <div className="remote-status-card">
          <span className="remote-label">Connection</span>
          <strong className={`remote-status remote-status-${overallStatus}`}>{overallStatus}</strong>
        </div>
        <div className="remote-status-card">
          <span className="remote-label">Guacamole</span>
          <strong>{guacamoleStatus}</strong>
        </div>
        <div className="remote-status-card">
          <span className="remote-label">xRDP target</span>
          <strong>{rdpStatus}</strong>
          <small>{remoteHealth?.rdp_host || config.rdp_host}:{remoteHealth?.rdp_port || 3389}</small>
        </div>
        <div className="remote-status-card">
          <span className="remote-label">Security</span>
          <strong>{config.security.replace('_', ' ')}</strong>
        </div>
      </div>

      {!config.enabled ? (
        <div className="remote-card remote-disabled">
          <h3>Remote desktop is disabled</h3>
          <p>Set <code>REMOTE_DESKTOP_ENABLED=true</code>, start the Guacamole stack, and keep Guacamole/xRDP reachable only over Tailscale or an authenticated same-origin dashboard proxy.</p>
          <pre>{`cd ~/jubilant-goggles
cp ops/remote-desktop/.env.example ops/remote-desktop/.env
# edit ops/remote-desktop/.env with the RDP password locally
docker compose -f ops/remote-desktop/docker-compose.guacamole.yml up -d`}</pre>
        </div>
      ) : (
        <div ref={frameShellRef} className={`remote-frame-shell ${isFullscreen ? 'remote-frame-shell-fullscreen' : ''}`}>
          <div className="remote-frame-toolbar">
            <div className="remote-frame-title">
              <span>Apache Guacamole</span>
              {autoLoginStatus && <small>{autoLoginStatus}</small>}
            </div>
            <div className="remote-frame-actions">
              <button className="btn-refresh" onClick={startGuacamoleSession}>
                <RefreshCw size={14} />
                Reconnect
              </button>
              <button className="btn-refresh" onClick={toggleFullscreen}>
                {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
                {isFullscreen ? 'Exit Full Screen' : 'Full Screen'}
              </button>
            </div>
          </div>
          {frameSrc ? (
            <iframe
              title="Apache Guacamole Remote Desktop"
              src={frameSrc}
              className="remote-frame"
              allow="fullscreen; clipboard-read; clipboard-write"
              allowFullScreen
            />
          ) : (
            <div className="remote-frame-loading">Opening remote desktop...</div>
          )}
        </div>
      )}
    </div>
  )
}

function EventTimeline({ events }: { events: SessionEvent[] }) {
  if (!events.length) return null
  return (
    <div className="event-timeline">
      {events.map((ev, i) => (
        <div key={ev.event_id || i} className="event-item">
          <div className="event-dot" data-type={ev.event_type} />
          <div className="event-body">
            <span className="event-type">{ev.event_type}</span>
            <span className="event-msg">{(ev.event_type === 'executor_finished' || ev.event_type === 'action_completed') ? <ReactMarkdown>{ev.data?.message || ''}</ReactMarkdown> : (ev.data?.message || '')}</span>
            <span className="event-time">{ev.timestamp?.slice(11, 19)}</span>
            {ev.data?.output && (ev.data?.type === 'tool_output' || ev.data?.type === 'plan_output') && (
              <details className="tool-output-details">
                <summary>{ev.data?.type === 'plan_output' ? 'Show agent-core plan' : 'Show output'}</summary>
                <pre className="tool-output">{ev.data.output}</pre>
              </details>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

function getProgressLabel(events: any[]): { stage: string; detail: string; icon: string } {
  if (!events || events.length === 0) return { stage: 'Starting', detail: 'Preparing...', icon: '\u23f3' }
  const last = events[events.length - 1]
  const et = last.event_type || ''
  const msg = last.data?.message || ''
  const tool = last.data?.tool || ''
  
  if (et === 'user_prompt_received') return { stage: 'Received', detail: 'Processing prompt...', icon: '\ud83d\udce8' }
  if (et === 'routing_decision_made') return { stage: 'Routing', detail: msg.slice(0, 80), icon: '\ud83d\udee4\ufe0f' }
  if (et === 'plan_requested') return { stage: 'Planning', detail: 'Requesting plan from agent-core...', icon: '\ud83e\udde0' }
  if (et === 'plan_generated') return { stage: 'Planned', detail: 'Plan ready', icon: '\ud83d\udccb' }
  if (et === 'action_started') return { stage: 'Starting executor', detail: msg, icon: '\u26a1' }
  if (et === 'executor_started') return { stage: 'Executor ready', detail: msg, icon: '\ud83d\ude80' }
  if (et === 'action_progress') {
    if (tool) return { stage: 'Running: ' + tool, detail: last.data?.args_summary || '', icon: '\ud83d\udd27' }
    if (msg.includes('iteration')) return { stage: msg, detail: '', icon: '\ud83d\udd04' }
    return { stage: 'Executing', detail: msg.slice(0, 80), icon: '\u2699\ufe0f' }
  }
  if (et === 'executor_finished') return { stage: 'Finishing', detail: 'Collecting results...', icon: '\u2705' }
  if (et === 'action_completed') return { stage: 'Complete', detail: '', icon: '\u2705' }
  if (et === 'action_failed') return { stage: 'Failed', detail: msg.slice(0, 80), icon: '\u274c' }
  if (et === 'action_blocked') return { stage: 'Blocked', detail: msg.slice(0, 80), icon: '\ud83d\udeab' }
  return { stage: et.replace(/_/g, ' '), detail: msg.slice(0, 60), icon: '\u2022' }
}

function TaskResult({ entry }: { entry: ChatEntry }) {
  const th = entry.taskHandle
  if (!th) {
    // Live progress mode - show events as they stream in
    if (entry.events && entry.events.length > 0) {
      const progress = getProgressLabel(entry.events)
      const toolEvents = entry.events.filter((ev: any) => ev.data?.tool)
      const totalEvents = entry.events.length
      return (
        <div className="task-result task-progress">
          <div className="progress-status">
            <span className="progress-icon">{progress.icon}</span>
            <span className="progress-stage">{progress.stage}</span>
            {progress.detail && <span className="progress-detail">{progress.detail}</span>}
            <span className="progress-count">{totalEvents} events</span>
          </div>
          <div className="progress-bar-container">
            <div className="progress-bar-fill" />
          </div>
          <details className="progress-events-toggle">
            <summary>Show {totalEvents} events ({toolEvents.length} tool calls)</summary>
            <div className="live-events">
              {entry.events.map((ev: any, i: number) => (
                <div key={i} className="live-event">
                  <span className="live-event-type">{ev.event_type}</span>
                  <span className="live-event-msg">{ev.data?.message || ''}</span>
                  {ev.data?.args_summary && <span className="live-event-args">{ev.data.args_summary}</span>}
                  {ev.data?.output && (ev.data?.type === 'tool_output' || ev.data?.type === 'plan_output') && (
                    <details className="tool-output-details">
                      <summary>{ev.data?.type === 'plan_output' ? 'Show agent-core plan' : 'Show output'}</summary>
                      <pre className="tool-output">{ev.data.output}</pre>
                    </details>
                  )}
                </div>
              ))}
            </div>
          </details>
        </div>
      )
    }
    return <div className="task-result task-progress"><div className="progress-status"><span className="progress-icon">{'\u23f3'}</span><span className="progress-stage">Starting</span><span className="progress-detail">Preparing...</span></div></div>
  }

  const stateColor = th.state === 'completed' ? '#4ade80' : th.state === 'blocked' ? '#fbbf24' : th.state === 'failed' ? '#f87171' : '#94a3b8'

  return (
    <div className="task-result">
      <div className="task-header">
        <span className="task-state" style={{ color: stateColor }}>{th.state}</span>
        <span className="task-routing">routing: {th.routing_decision}</span>
        {th.metadata?.executor && <span className="task-executor">executor: {th.metadata.executor}</span>}
      </div>
      <div className="task-message"><ReactMarkdown>{th.message}</ReactMarkdown></div>
      {th.plan_summary && (
        <details className="task-plan">
          <summary>Plan</summary>
          <pre>{th.plan_summary}</pre>
        </details>
      )}
      {th.error && <div className="task-error">{th.error}</div>}
      {((th.metadata?.commands_run?.length ?? 0) > 0 || (th.metadata?.files_edited?.length ?? 0) > 0) && (
        <details className="task-output">
          <summary>Output ({th.metadata?.commands_run?.length || 0} commands, {th.metadata?.files_edited?.length || 0} files edited)</summary>
          <div className="output-details">
            {(th.metadata?.commands_run?.length ?? 0) > 0 && (
              <div><strong>Commands:</strong><pre className="output-pre">{th.metadata!.commands_run!.join('\n')}</pre></div>
            )}
            {(th.metadata?.files_edited?.length ?? 0) > 0 && (
              <div><strong>Files edited:</strong><pre className="output-pre">{th.metadata!.files_edited!.join('\n')}</pre></div>
            )}
            {th.metadata?.duration_seconds && <div className="output-meta">Duration: {th.metadata.duration_seconds.toFixed(1)}s</div>}
          </div>
        </details>
      )}
      {entry.events && entry.events.length > 0 && (
        <details className="task-events" open>
          <summary>Events ({entry.events.length})</summary>
          <EventTimeline events={entry.events} />
        </details>
      )}
    </div>
  )
}

interface BrowseEntry {
  name: string
  path: string
  is_dir: boolean
  is_repo: boolean
}

interface ServiceInfo {
  name: string
  port: number
  description: string
  status: 'running' | 'stopped'
  pid: number | null
  docker?: boolean
  repo_backed?: boolean
  update_supported?: boolean
  update_in_progress?: boolean
  last_update?: { commit: string; timestamp: string; status: string } | null
  can_start?: boolean
  can_stop?: boolean
  can_restart?: boolean
}

function PortManager() {
  const [services, setServices] = useState<ServiceInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [updateLoading, setUpdateLoading] = useState<Record<string, boolean>>({})
  const [updateError, setUpdateError] = useState<Record<string, string>>({})
  const [updateSuccess, setUpdateSuccess] = useState<Record<string, string>>({})

  const fetchServices = useCallback(() => {
    fetch(`${CONTROL_API}/services`)
      .then(r => r.json())
      .then(data => setServices(data.services || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    fetchServices()
    const id = setInterval(fetchServices, 5000)
    return () => clearInterval(id)
  }, [fetchServices])

  const waitForServiceStatus = async (name: string, status: ServiceInfo['status'], attempts = 10) => {
    for (let attempt = 0; attempt < attempts; attempt++) {
      const response = await fetch(`${CONTROL_API}/services`)
      const data = await response.json()
      const nextServices = data.services || []
      setServices(nextServices)
      if (nextServices.find((svc: ServiceInfo) => svc.name === name)?.status === status) {
        return
      }
      await new Promise(r => setTimeout(r, 1000))
    }
  }

  const startService = async (name: string) => {
    setActionLoading(`${name}:start`)
    try {
      await fetch(`${CONTROL_API}/services/${name}/start`, { method: 'POST' })
      await waitForServiceStatus(name, 'running')
      if (name === 'dashboard') window.location.reload()
    } catch {}
    setActionLoading(null)
  }

  const stopService = async (name: string) => {
    setActionLoading(`${name}:stop`)
    try {
      await fetch(`${CONTROL_API}/services/${name}/stop`, { method: 'POST' })
      await waitForServiceStatus(name, 'stopped')
    } catch {}
    setActionLoading(null)
  }

  const updateLatest = async (name: string) => {
    setUpdateLoading(prev => ({ ...prev, [name]: true }))
    setUpdateError(prev => { const n = { ...prev }; delete n[name]; return n })
    setUpdateSuccess(prev => { const n = { ...prev }; delete n[name]; return n })
    try {
      const res = await fetch(`${CONTROL_API}/v2/services/${name}/update-latest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ restart: true }),
      })
      const data = await res.json()
      if (data.ok) {
        setUpdateSuccess(prev => ({ ...prev, [name]: data.message || 'Updated' }))
      } else {
        setUpdateError(prev => ({ ...prev, [name]: data.error?.message || 'Update failed' }))
      }
      fetchServices()
    } catch {
      setUpdateError(prev => ({ ...prev, [name]: 'Network error' }))
    }
    setUpdateLoading(prev => ({ ...prev, [name]: false }))
  }

  const restartService = async (name: string) => {
    setActionLoading(`${name}:restart`)
    try {
      await fetch(`${CONTROL_API}/services/${name}/restart`, { method: 'POST' })
      await waitForServiceStatus(name, 'running', name === 'control-plane' ? 15 : 10)
      if (name === 'dashboard' || name === 'control-plane') window.location.reload()
    } catch {}
    setActionLoading(null)
  }

  if (loading) return <div className="port-manager"><div className="pm-loading">Discovering services...</div></div>

  return (
    <div className="port-manager">
      <div className="pm-header">
        <Server size={16} />
        <span>Services</span>
        <button className="pm-refresh" onClick={fetchServices} title="Refresh">
          <RefreshCw size={14} />
        </button>
      </div>
      <div className="pm-list">
        {services.map(svc => (
          <div key={svc.name} className={`pm-item pm-${svc.status}`}>
            <div className="pm-item-info">
              <Circle size={8} fill={svc.status === 'running' ? '#4ade80' : '#94a3b8'} stroke={svc.status === 'running' ? '#4ade80' : '#94a3b8'} />
              <span className="pm-name">{svc.name}</span>
              <span className="pm-port">:{svc.port}</span>
              {svc.docker && <span className="pm-docker">docker</span>}
            </div>
            <div className="pm-item-desc">{svc.description}</div>
            {updateError[svc.name] && <div className="pm-update-msg pm-update-error">{updateError[svc.name]}</div>}
            {updateSuccess[svc.name] && <div className="pm-update-msg pm-update-success">{updateSuccess[svc.name]}</div>}
            <div className="pm-item-actions">
              {actionLoading?.startsWith(`${svc.name}:`) ? (
                <span className="pm-busy">...</span>
              ) : svc.status === 'running' ? (
                <>
                  {svc.can_restart !== false && (
                    <button className="pm-btn pm-btn-restart" onClick={() => restartService(svc.name)} title="Restart">
                      <RefreshCw size={12} />
                    </button>
                  )}
                  {svc.repo_backed && (
                    <button
                      className={`pm-btn pm-btn-update${updateLoading[svc.name] ? ' pm-btn-updating' : ''}`}
                      onClick={() => updateLatest(svc.name)}
                      disabled={!svc.update_supported || updateLoading[svc.name] || svc.update_in_progress}
                      title={!svc.update_supported ? 'GitHub token not configured on server' : 'Update latest from GitHub'}
                    >
                      <Download size={12} className={updateLoading[svc.name] ? 'pm-spin' : ''} />
                    </button>
                  )}
                  {svc.can_stop !== false && (
                    <button className="pm-btn pm-btn-stop" onClick={() => stopService(svc.name)} title="Stop">
                      <Power size={12} />
                    </button>
                  )}
                </>
              ) : (
                <>
                  {svc.can_start !== false && (
                    <button className="pm-btn pm-btn-start" onClick={() => startService(svc.name)} title="Start">
                      <Power size={12} />
                    </button>
                  )}
                  {svc.repo_backed && (
                    <button
                      className={`pm-btn pm-btn-update${updateLoading[svc.name] ? ' pm-btn-updating' : ''}`}
                      onClick={() => updateLatest(svc.name)}
                      disabled={!svc.update_supported || updateLoading[svc.name] || svc.update_in_progress}
                      title={!svc.update_supported ? 'GitHub token not configured on server' : 'Update latest from GitHub'}
                    >
                      <Download size={12} className={updateLoading[svc.name] ? 'pm-spin' : ''} />
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function FolderBrowser({ onSelect }: { onSelect: (path: string) => void }) {
  const [currentPath, setCurrentPath] = useState('/opt/workstation/repos')
  const [entries, setEntries] = useState<BrowseEntry[]>([])
  const [parentPath, setParentPath] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const browse = useCallback((path: string) => {
    setLoading(true)
    fetch(`${API}/browse?path=${encodeURIComponent(path)}`)
      .then(r => r.json())
      .then(data => {
        setCurrentPath(data.path || path)
        setEntries(data.entries || [])
        setParentPath(data.parent || null)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { browse(currentPath) }, [])

  return (
    <div className="folder-browser">
      <div className="browser-header">
        <span className="browser-path">{currentPath}</span>
      </div>
      <div className="browser-entries">
        {parentPath && currentPath !== '/' && (
          <div className="browser-entry" onClick={() => browse(parentPath)}>
            <ArrowUp size={16} className="entry-icon-svg" />
            <span className="entry-name">..</span>
          </div>
        )}
        {loading && <div className="browser-loading">Loading...</div>}
        {entries.map(entry => (
          <div
            key={entry.path}
            className={`browser-entry ${entry.is_repo ? 'is-repo' : ''}`}
            onClick={() => entry.is_repo ? onSelect(entry.path) : browse(entry.path)}
          >
            {entry.is_repo ? (
              <GitBranch size={16} className="entry-icon-svg repo-icon" />
            ) : (
              <Folder size={16} className="entry-icon-svg" />
            )}
            <span className="entry-name">{entry.name}</span>
            {entry.is_repo && <span className="entry-badge">repo</span>}
          </div>
        ))}
        {!loading && entries.length === 0 && <div className="browser-empty">Empty directory</div>}
      </div>
    </div>
  )
}

function openNativePicker(onSelect: (path: string) => void, setPickerLoading: (v: boolean) => void) {
  setPickerLoading(true)
  fetch(`${API}/pick-folder`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ start_path: '/opt/workstation/repos' }) })
    .then(r => r.json())
    .then(data => {
      if (data.selected && data.path) {
        onSelect(data.path)
      }
    })
    .catch(() => {})
    .finally(() => setPickerLoading(false))
}

export default function App() {
  // Inject live-event styles
  if (!document.getElementById('live-event-styles')) {
    const s = document.createElement('style')
    s.id = 'live-event-styles'
    s.textContent = `
.task-progress { border-left: 3px solid #60a5fa; }
.tool-output-details { margin: 4px 0; }
.tool-output-details summary { cursor: pointer; font-size: 12px; color: #6366f1; font-weight: 500; padding: 2px 0; user-select: none; }
.tool-output-details summary:hover { color: #4f46e5; }
.tool-output { background: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px 12px; margin: 4px 0; font-size: 12px; font-family: monospace; white-space: pre-wrap; word-break: break-all; max-height: 300px; overflow-y: auto; color: #334155; line-height: 1.4; }
.live-events { display: flex; flex-direction: column; gap: 4px; padding: 8px 0; max-height: 300px; overflow-y: auto; }
.live-event { display: flex; gap: 8px; align-items: baseline; font-size: 12px; padding: 2px 0; }
.live-event-type { font-family: monospace; font-size: 11px; color: #6366f1; min-width: 120px; }
.live-event-msg { color: #374151; flex: 1; }
.live-event-args { font-family: monospace; font-size: 11px; color: #6b7280; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.task-message { background: #f8fafc; padding: 12px 16px; border-radius: 8px; font-size: 14px; line-height: 1.6; color: #1e293b; overflow-x: auto; white-space: normal; }
.task-message h2 { font-size: 16px; margin: 8px 0 4px; color: #1e293b; }
.task-message h3 { font-size: 14px; margin: 6px 0 2px; color: #334155; }
.task-message p { margin: 4px 0; }
.task-message ul, .task-message ol { margin: 4px 0; padding-left: 20px; }
.task-message li { margin: 2px 0; }
.task-message code { background: #e2e8f0; padding: 1px 4px; border-radius: 3px; font-size: 13px; }
.task-message pre { background: #1e293b; color: #e2e8f0; padding: 8px 12px; border-radius: 6px; overflow-x: auto; }
.task-message pre code { background: none; padding: 0; color: inherit; }
.task-message strong { color: #0f172a; }
.task-message a { color: #6366f1; text-decoration: underline; }
.event-msg p { margin: 0; display: inline; }
.event-msg h2, .event-msg h3 { font-size: 13px; margin: 2px 0; }
.event-msg ul { margin: 2px 0; padding-left: 16px; font-size: 12px; }
`
    document.head.appendChild(s)
  }

  const [sessionId, setSessionId] = useState<string | null>(null)
  const [sessions, setSessions] = useState<{ id: string; status: string; repo_path: string; created_at: string }[]>([])
  const [chat, setChat] = useState<ChatEntry[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [executionMode, setExecutionMode] = useState<'finite' | 'open_ended' | 'loop'>('finite')
  const [health, setHealth] = useState<Health | null>(null)
  const [newSessionRepo, setNewSessionRepo] = useState('agent-core')
  const [showSidebar, setShowSidebar] = useState(false)
  const [showBrowser, setShowBrowser] = useState(true)
  const [showPortManager, setShowPortManager] = useState(true)
  const [pickerLoading, setPickerLoading] = useState(false)
  const [routePath, setRoutePath] = useState(window.location.pathname)
  const chatEndRef = useRef<HTMLDivElement>(null)

  const navigate = useCallback((path: string) => {
    window.history.pushState({}, '', path)
    setRoutePath(path)
  }, [])

  useEffect(() => {
    const handlePopState = () => setRoutePath(window.location.pathname)
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  // Fetch health
  useEffect(() => {
    const fetchHealth = () => fetch(`${API}/health`).then(r => r.json()).then(setHealth).catch(() => {})
    fetchHealth()
    const id = setInterval(fetchHealth, 10000)
    return () => clearInterval(id)
  }, [])

  // Fetch sessions
  const fetchSessions = useCallback(() => {
    fetch(`${API}/sessions`).then(r => r.json()).then(d => setSessions(d.sessions || [])).catch(() => {})
  }, [])

  useEffect(() => { fetchSessions() }, [fetchSessions])

  // Scroll to bottom
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [chat])

  const createSession = async () => {
    const name = `session-${Date.now().toString(36)}`
    const res = await fetch(`${API}/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, repo: newSessionRepo }),
    })
    const data = await res.json()
    if (data.id) {
      setSessionId(data.id)
      setChat([{
        id: generateUUID(),
        role: 'system',
        content: `Session created: ${data.id} (repo: ${data.repo_path})`,
        timestamp: new Date().toISOString(),
      }])
      fetchSessions()
      setShowSidebar(false)
    }
  }

  const selectSession = async (id: string) => {
    setSessionId(id)
    setShowSidebar(false)
    // Load existing events as chat history
    try {
      const evRes = await fetch(`${API}/sessions/${id}/events`)
      const evData = await evRes.json()
      if (evData.events?.length > 0) {
        setChat([{
          id: generateUUID(),
          role: 'system',
          content: `Resumed session: ${id} (${evData.total} events)`,
          timestamp: new Date().toISOString(),
          events: evData.events,
        }])
      } else {
        setChat([{
          id: generateUUID(),
          role: 'system',
          content: `Selected session: ${id}`,
          timestamp: new Date().toISOString(),
        }])
      }
    } catch {
      setChat([{ id: generateUUID(), role: 'system', content: `Selected session: ${id}`, timestamp: new Date().toISOString() }])
    }
  }

  const sendMessage = async () => {
    if (!input.trim() || sending || !sessionId) return
    const instruction = input.trim()
    setInput('')
    setSending(true)

    const userEntry: ChatEntry = {
      id: generateUUID(),
      role: 'user',
      content: instruction,
      timestamp: new Date().toISOString(),
    }
    setChat(prev => [...prev, userEntry])

    // Show live progress entry immediately
    const progressId = generateUUID()
    const progressEntry: ChatEntry = {
      id: progressId,
      role: 'system',
      content: 'Working...',
      timestamp: new Date().toISOString(),
      events: [],
    }
    setChat(prev => [...prev, progressEntry])

    // Start polling events while request is in-flight
    let lastSeq = 0
    let polling = true
    const pollEvents = async () => {
      while (polling) {
        try {
          const evRes = await fetch(`${API}/sessions/${sessionId}/events/stream?after=${lastSeq}`)
          const evData = await evRes.json()
          if (evData.events && evData.events.length > 0) {
            lastSeq = evData.total
            setChat(prev => prev.map(e => 
              e.id === progressId 
                ? { ...e, events: [...(e.events || []), ...evData.events], content: evData.events[evData.events.length - 1]?.data?.message || e.content }
                : e
            ))
          }
        } catch {}
        await new Promise(r => setTimeout(r, 800))
      }
    }
    pollEvents()

    try {
      const res = await fetch(`${API}/sessions/${sessionId}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instruction, execution_mode: executionMode }),
      })
      const taskHandle: TaskHandle = await res.json()

      // If server returned "working", poll /chat/status until done
      if (taskHandle.state === 'working') {
        let done = false
        while (!done) {
          await new Promise(r => setTimeout(r, 2000))
          try {
            const statusRes = await fetch(`${API}/sessions/${sessionId}/chat/status`)
            const statusData = await statusRes.json()
            if (statusData.state !== 'working') {
              done = true
              Object.assign(taskHandle, statusData)
            }
          } catch {}
        }
      }

      polling = false

      // Final events fetch
      let events: SessionEvent[] = []
      try {
        const evRes = await fetch(`${API}/sessions/${sessionId}/events`)
        const evData = await evRes.json()
        events = evData.events || []
      } catch {}

      let sessionState: SessionState | undefined
      try {
        const stRes = await fetch(`${API}/sessions/${sessionId}/state`)
        sessionState = await stRes.json()
      } catch {}

      // Replace progress entry with final result
      setChat(prev => prev.map(e => 
        e.id === progressId
          ? { ...e, content: taskHandle.message || 'Task processed.', taskHandle, events, sessionState }
          : e
      ))
    } catch (err: any) {
      polling = false
      setChat(prev => prev.map(e =>
        e.id === progressId
          ? { ...e, content: `Error: ${(err as Error).message}` }
          : e
      ))
    } finally {
      setSending(false)
    }
  }

  const destroySession = async (id: string) => {
    await fetch(`${API}/sessions/${id}`, { method: 'DELETE' })
    fetchSessions()
    if (sessionId === id) {
      setSessionId(null)
      setChat([])
    }
  }

  return (
    <div className="app">
      {/* Header */}
      <header className="header">
        <div className="header-left">
          <button className="sidebar-toggle" onClick={() => setShowSidebar(!showSidebar)}>
            <Menu size={20} />
          </button>
          <h1 className="logo" onClick={() => { navigate('/'); setSessionId(null); setChat([]) }} style={{ cursor: 'pointer' }}>Control Plane</h1>
        </div>
        <div className="header-right">
          <button className="nav-link" onClick={() => navigate('/remote-desktop')}>
            <Monitor size={14} />
            Remote Desktop
          </button>
          {health && (
            <div className="health-strip">
              <StatusDot status={health.agent_core?.status || 'unknown'} /><span>agent-core</span>
              <StatusDot status={health.litellm?.status || 'unknown'} /><span>LiteLLM</span>
              <StatusDot status={health.openhands?.status || 'unknown'} /><span>OpenHands</span>
              <span className="health-ports">{health.active_ports?.join(', ')}</span>
            </div>
          )}
        </div>
      </header>

      {/* Sidebar */}
      {showSidebar && (
        <div className="sidebar-overlay" onClick={() => setShowSidebar(false)}>
          <div className="sidebar" onClick={e => e.stopPropagation()}>
            <h3>Sessions</h3>
            <div className="new-session">
              <select value={newSessionRepo} onChange={e => setNewSessionRepo(e.target.value)}>
                <option value="agent-core">agent-core</option>
                <option value="jubilant-goggles">jubilant-goggles</option>
              </select>
              <button className="btn-create" onClick={createSession}>+ New Session</button>
            </div>
            <div className="session-list">
              {sessions.map(s => (
                <div key={s.id} className={`session-item ${s.id === sessionId ? 'active' : ''}`}>
                  <div className="session-item-main" onClick={() => selectSession(s.id)}>
                    <span className="session-name">{s.id}</span>
                    <span className="session-meta">{s.repo_path?.split('/').pop()}</span>
                  </div>
                  <button className="btn-destroy" onClick={() => destroySession(s.id)}><X size={14} /></button>
                </div>
              ))}
              {sessions.length === 0 && <p className="empty">No sessions yet</p>}
            </div>
          </div>
        </div>
      )}

      {/* Main chat area */}
      <main className="main">
        {routePath === '/remote-desktop' ? (
          <RemoteDesktopPage />
        ) : !sessionId ? (
          <div className="welcome">
            <h2>Workstation Agent</h2>
            <p>Create or select a session to start working.</p>
            <div className="welcome-actions">
              <div className="repo-input-row">
                <input
                  className="repo-input"
                  value={newSessionRepo}
                  onChange={e => setNewSessionRepo(e.target.value)}
                  placeholder="Repo name or path..."
                />
                <button className="btn-browse" onClick={() => setShowBrowser(!showBrowser)}>
                  <Folder size={14} />
                  {showBrowser ? 'Close' : 'Browse...'}
                </button>
              </div>
              <button className="btn-start" onClick={createSession}>Start Session</button>
            </div>
            {showBrowser && (
              <FolderBrowser onSelect={(path) => { setNewSessionRepo(path); setShowBrowser(false) }} />
            )}
            <PortManager />
          </div>
        ) : (
          <div className="chat-area">
            <div className="chat-messages">
              {chat.map(entry => (
                <div key={entry.id} className={`chat-entry chat-${entry.role}`}>
                  {entry.role === 'user' ? (
                    <div className="msg-bubble user-bubble">
                      <div className="msg-text">{entry.content}</div>
                    </div>
                  ) : (
                    <div className="msg-bubble system-bubble">
                      <TaskResult entry={entry} />
                    </div>
                  )}
                </div>
              ))}

              <div ref={chatEndRef} />
            </div>

            {/* Input */}
            <div className="chat-input-area">
              <div className="mode-selector">
                {(['finite', 'open_ended', 'loop'] as const).map(mode => (
                  <button
                    key={mode}
                    className={`mode-btn ${executionMode === mode ? 'mode-active' : ''}`}
                    onClick={() => setExecutionMode(mode)}
                    disabled={sending}
                    title={mode === 'finite' ? 'Limited iterations (50 max)' : mode === 'open_ended' ? 'No limit - runs until agent finishes' : 'Continuous loop with checkpoints'}
                  >
                    {mode === 'finite' ? '\u23f1 Finite' : mode === 'open_ended' ? '\u267e Open' : '\ud83d\udd01 Loop'}
                  </button>
                ))}
              </div>
              <div className="input-wrapper">
                <input
                  className="chat-input"
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && !e.shiftKey && sendMessage()}
                  placeholder="What would you like to do?"
                  disabled={sending}
                  autoFocus
                />
                <button className="btn-send" onClick={sendMessage} disabled={sending || !input.trim()}>
                  <Send size={20} />
                </button>
              </div>
              <div className="input-meta">
                Session: <strong>{sessionId}</strong> | {executionMode === 'finite' ? '50 iterations max' : executionMode === 'open_ended' ? 'No iteration limit' : 'Continuous loop'} | Press Enter to send
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
