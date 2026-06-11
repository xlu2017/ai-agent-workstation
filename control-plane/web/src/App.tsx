import { useState, useEffect, useRef, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import {
  Send, ChevronLeft, ChevronRight, ChevronDown, Folder, GitBranch, Plus, X, Circle,
  Clock, ArrowUp, Power, RefreshCw, Server, Monitor, Maximize2,
  Minimize2, Download, Search, MoreHorizontal, Settings, HelpCircle, LogOut, UserPlus,
  Eye, Layers, MessageSquare, BookOpen, Sparkles, Check, Filter, SortAsc, Archive,
  Zap, Shield, Key, FileText, Users, BarChart3, Terminal,
  Cpu, Lock, Play,
} from 'lucide-react'
import AgentSessionPage from './AgentSessionPage'
import SessionGraphExplorer from './components/session-graph/SessionGraphExplorer'
import './agent-session.css'

// ─── helpers ──────────────────────────────────────────────────────────────────

function generateUUID(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = (Math.random() * 16) | 0
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
  })
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function truncStr(s: string, n: number): string {
  return s.length > n ? s.slice(0, n) + '…' : s
}

// ─── types ────────────────────────────────────────────────────────────────────

interface TaskHandle {
  task_id: string; session_id: string; state: string; message: string
  routing_decision: string; plan_summary: string; error: string; events_path: string
  metadata: { files_edited?: string[]; executor?: string; duration_seconds?: number; commands_run?: string[]; tests_passed?: number; tests_failed?: number }
}

interface SessionEvent {
  event_type: string; session_id: string; data: Record<string, any>
  event_id: string; timestamp: string; sequence: number
}

interface SessionState { state: string; last_event: string; total_events: number }

interface Health {
  agent_core: { status: string; error?: string }
  litellm: { status: string; url?: string; error?: string }
  vendor_runtime: { status: string; error?: string }
  bridge: { status: string; error?: string }
  disk: { used: string; available: string; percent: string }
  memory: { total: string; used: string; available: string }
  cpu: { load_1m: string; load_5m: string; load_15m: string }
  active_ports: number[]
}

interface RemoteDesktopConfig {
  enabled: boolean; provider: string; url: string; rdp_host: string; security: string; auto_login: boolean
}
interface RemoteDesktopHealth {
  ok: boolean; enabled: boolean; provider: string; guacamole: string; guacd: string; rdp: string; rdp_host: string; rdp_port: number
}

interface ChatEntry {
  id: string; role: 'user' | 'system'; content: string; timestamp: string
  taskHandle?: TaskHandle; events?: SessionEvent[]; sessionState?: SessionState
}
interface SessionRecord { id: string; status: string; repo_path: string; created_at: string }
interface BrowseEntry { name: string; path: string; is_dir: boolean; is_repo: boolean }
interface ServiceInfo {
  name: string; port: number; description: string; status: 'running' | 'stopped'; pid: number | null
  docker?: boolean; repo_backed?: boolean; update_supported?: boolean; update_in_progress?: boolean
  last_update?: { commit: string; timestamp: string; status: string } | null
  can_start?: boolean; can_stop?: boolean; can_restart?: boolean
}
interface GuacamoleSession {
  authToken: string; username: string; dataSource: string; availableDataSources: string[]; connection_url: string
}

const API = '/api'
const CONTROL_API = window.location.port === '5173'
  ? `${window.location.protocol}//${window.location.hostname}:9877/api`
  : API

// ─── hooks ────────────────────────────────────────────────────────────────────

function useClickOutside(ref: React.RefObject<HTMLElement | null>, handler: () => void) {
  useEffect(() => {
    const fn = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) handler() }
    document.addEventListener('mousedown', fn)
    return () => document.removeEventListener('mousedown', fn)
  }, [ref, handler])
}

function useEscapeKey(handler: () => void, active = true) {
  useEffect(() => {
    if (!active) return
    const fn = (e: KeyboardEvent) => { if (e.key === 'Escape') handler() }
    document.addEventListener('keydown', fn)
    return () => document.removeEventListener('keydown', fn)
  }, [handler, active])
}

// ─── workspace dropdown ───────────────────────────────────────────────────────

function WorkspaceDropdown({ workspaceName, open, onClose, onSettings }: {
  workspaceName: string; open: boolean; onClose: () => void; onSettings: () => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  useClickOutside(ref, onClose)
  useEscapeKey(onClose, open)
  if (!open) return null
  return (
    <div className="ws-dropdown" ref={ref} role="menu" aria-label="Workspace menu">
      <div className="ws-dropdown-header">
        <div className="ws-dropdown-identity">
          <div className="ws-avatar">{workspaceName.charAt(0).toUpperCase()}</div>
          <div className="ws-identity-text">
            <span className="ws-identity-name">{workspaceName}</span>
            <span className="ws-identity-sub">Organization</span>
          </div>
        </div>
        <div className="ws-dropdown-header-actions">
          <button className="ws-btn-sm" onClick={onSettings} aria-label="Settings"><Settings size={14} /> Settings</button>
          <button className="ws-btn-sm" aria-label="Invite members" disabled><UserPlus size={14} /> Invite</button>
        </div>
      </div>
      <div className="ws-dropdown-section"><span className="ws-section-label">Team &amp; Personal</span></div>
      <div className="ws-dropdown-rows">
        <div className="ws-workspace-row active" role="menuitem">
          <div className="ws-row-avatar">{workspaceName.charAt(0).toUpperCase()}</div>
          <span className="ws-row-name">{workspaceName}</span>
          <Check size={14} className="ws-check" />
        </div>
      </div>
      <div className="ws-dropdown-footer">
        <button className="ws-footer-btn" role="menuitem" aria-label="Create new workspace"><Plus size={14} /> Create new workspace</button>
        <button className="ws-footer-btn ws-logout" role="menuitem" aria-label="Log out"><LogOut size={14} /> Log out</button>
      </div>
    </div>
  )
}

// ─── recent sessions overflow menu ────────────────────────────────────────────

function RecentMenu({ open, onClose, sortBy, onSortChange, filters, onFilterToggle }: {
  open: boolean; onClose: () => void
  sortBy: 'created' | 'updated'; onSortChange: (v: 'created' | 'updated') => void
  filters: { schedules: boolean; archived: boolean; automations: boolean }
  onFilterToggle: (key: 'schedules' | 'archived' | 'automations') => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  useClickOutside(ref, onClose)
  useEscapeKey(onClose, open)
  if (!open) return null
  return (
    <div className="recent-menu" ref={ref} role="menu" aria-label="Session options">
      <div className="recent-menu-section">
        <span className="recent-menu-label"><SortAsc size={12} /> Sort by</span>
        <button className="recent-menu-item" onClick={() => onSortChange('created')} role="menuitemradio" aria-checked={sortBy === 'created'}>Created time {sortBy === 'created' && <Check size={12} />}</button>
        <button className="recent-menu-item" onClick={() => onSortChange('updated')} role="menuitemradio" aria-checked={sortBy === 'updated'}>Last updated {sortBy === 'updated' && <Check size={12} />}</button>
      </div>
      <div className="recent-menu-section">
        <span className="recent-menu-label"><Filter size={12} /> Filter</span>
        <label className="recent-menu-toggle"><input type="checkbox" checked={filters.schedules} onChange={() => onFilterToggle('schedules')} /><span>Schedules</span></label>
        <label className="recent-menu-toggle"><input type="checkbox" checked={filters.archived} onChange={() => onFilterToggle('archived')} /><span>Archived</span></label>
        <label className="recent-menu-toggle"><input type="checkbox" checked={filters.automations} onChange={() => onFilterToggle('automations')} /><span>Automations</span></label>
      </div>
      <div className="recent-menu-section recent-menu-actions">
        <button className="recent-menu-item" role="menuitem"><Eye size={12} /> View all sessions</button>
        <button className="recent-menu-item" role="menuitem" disabled><Archive size={12} /> Archive all sessions</button>
      </div>
    </div>
  )
}

// ─── settings page ────────────────────────────────────────────────────────────

const SETTINGS_GROUPS = [
  { label: 'Organization', items: [
    { key: 'general', label: 'General', icon: <Settings size={16} /> },
    { key: 'connections', label: 'Connections', icon: <Zap size={16} /> },
    { key: 'sessions', label: 'Sessions', icon: <Layers size={16} /> },
    { key: 'plans', label: 'Plans', icon: <FileText size={16} /> },
    { key: 'invoices', label: 'Invoices', icon: <FileText size={16} /> },
    { key: 'usage', label: 'Usage & limits', icon: <BarChart3 size={16} /> },
  ]},
  { label: 'Products', items: [
    { key: 'agent', label: 'Agent', icon: <Cpu size={16} /> },
    { key: 'review', label: 'Review', icon: <Eye size={16} /> },
    { key: 'knowledge', label: 'Knowledge', icon: <BookOpen size={16} /> },
    { key: 'schedules', label: 'Schedules', icon: <Clock size={16} /> },
    { key: 'remote-desktop', label: 'Remote Desktop', icon: <Monitor size={16} />, badge: 'New' },
  ]},
  { label: 'Resources', items: [
    { key: 'skills', label: 'Skills & Rules', icon: <Shield size={16} /> },
    { key: 'environment', label: 'Environment', icon: <Terminal size={16} /> },
    { key: 'playbooks', label: 'Playbooks', icon: <Play size={16} /> },
    { key: 'secrets', label: 'Secrets', icon: <Lock size={16} /> },
  ]},
  { label: 'Administration', items: [
    { key: 'repositories', label: 'Repositories', icon: <GitBranch size={16} /> },
    { key: 'membership', label: 'Membership', icon: <Users size={16} /> },
    { key: 'api', label: 'API', icon: <Key size={16} /> },
    { key: 'analytics', label: 'Analytics', icon: <BarChart3 size={16} /> },
  ]},
]

function SettingsPage({ workspaceName, onBack }: { workspaceName: string; onBack: () => void }) {
  const [search, setSearch] = useState('')
  const [activeKey, setActiveKey] = useState('general')
  const filteredGroups = SETTINGS_GROUPS.map(g => ({
    ...g, items: g.items.filter(it => it.label.toLowerCase().includes(search.toLowerCase())),
  })).filter(g => g.items.length > 0)

  return (
    <div className="settings-page">
      <aside className="settings-sidebar">
        <button className="settings-back" onClick={onBack} aria-label="Back to app"><ChevronLeft size={14} /> Back to app</button>
        <div className="settings-search-wrap"><Search size={12} /><input className="settings-search" placeholder="Search settings..." value={search} onChange={e => setSearch(e.target.value)} aria-label="Search settings" /></div>
        <nav className="settings-nav" aria-label="Settings navigation">
          <div className="settings-nav-section">
            <span className="settings-nav-label">Personal</span>
            <button className={`settings-nav-item ${activeKey === 'preferences' ? 'active' : ''}`} onClick={() => setActiveKey('preferences')}>Preferences</button>
            <button className={`settings-nav-item ${activeKey === 'personal-connections' ? 'active' : ''}`} onClick={() => setActiveKey('personal-connections')}>Connections</button>
          </div>
          <div className="settings-nav-section">
            <span className="settings-nav-label">Organization</span>
            {SETTINGS_GROUPS.flatMap(g => g.items).filter(it => it.label.toLowerCase().includes(search.toLowerCase())).map(it => (
              <button key={it.key} className={`settings-nav-item ${activeKey === it.key ? 'active' : ''}`} onClick={() => setActiveKey(it.key)}>
                {it.label}
                {it.badge && <span className="settings-badge">{it.badge}</span>}
              </button>
            ))}
          </div>
        </nav>
      </aside>
      <main className="settings-main">
        <div className="settings-content">
          <h1 className="settings-title">{workspaceName}</h1>
          <p className="settings-subtitle">Organization preferences and settings</p>
          {filteredGroups.map(g => (
            <div key={g.label} className="settings-group">
              <h3 className="settings-group-label">{g.label}</h3>
              <div className="settings-card">
                {g.items.map(it => (
                  <button key={it.key} className={`settings-row ${activeKey === it.key ? 'active' : ''}`} onClick={() => setActiveKey(it.key)} aria-label={it.label}>
                    <div className="settings-row-icon">{it.icon}</div>
                    <span className="settings-row-label">{it.label}</span>
                    {it.badge && <span className="settings-badge">{it.badge}</span>}
                    <ChevronRight size={14} className="settings-row-chevron" />
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </main>
    </div>
  )
}

// ─── remote desktop page ──────────────────────────────────────────────────────

function RemoteDesktopPage() {
  const [config, setConfig] = useState<RemoteDesktopConfig | null>(null)
  const [remoteHealth, setRemoteHealth] = useState<RemoteDesktopHealth | null>(null)
  const [error, setError] = useState('')
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [frameSrc, setFrameSrc] = useState('')
  const [autoLoginStatus, setAutoLoginStatus] = useState('')
  const frameShellRef = useRef<HTMLDivElement>(null)

  const refresh = useCallback(() => {
    fetch(`${API}/v2/remote-desktop/config`).then(r => r.json()).then(setConfig).catch(err => setError((err as Error).message))
    fetch(`${API}/v2/remote-desktop/health`).then(r => r.json()).then(setRemoteHealth).catch(() => {})
  }, [])

  useEffect(() => { refresh(); const id = setInterval(refresh, 10000); return () => clearInterval(id) }, [refresh])

  useEffect(() => {
    const fn = () => { setIsFullscreen(document.fullscreenElement === frameShellRef.current) }
    document.addEventListener('fullscreenchange', fn)
    return () => document.removeEventListener('fullscreenchange', fn)
  }, [])

  const toggleFullscreen = useCallback(() => {
    const el = frameShellRef.current
    if (!el) return
    if (document.fullscreenElement) { document.exitFullscreen().catch(e => setError((e as Error).message)); return }
    el.requestFullscreen().catch(e => setError((e as Error).message))
  }, [])

  const startGuacamoleSession = useCallback(() => {
    if (!config?.enabled) return
    if (!config.auto_login) { setFrameSrc(config.url); setAutoLoginStatus(''); return }
    setAutoLoginStatus('Signing in...')
    fetch(`${API}/v2/remote-desktop/token`, { method: 'POST' })
      .then(async r => { if (!r.ok) throw new Error(await r.text() || 'Unable to sign in'); return r.json() as Promise<GuacamoleSession> })
      .then(session => {
        localStorage.setItem('GUAC_AUTH', JSON.stringify({ authToken: session.authToken, username: session.username, dataSource: session.dataSource, availableDataSources: session.availableDataSources }))
        setFrameSrc(session.connection_url || config.url)
        setAutoLoginStatus('Signed in')
      })
      .catch(err => { setAutoLoginStatus(`Auto-login failed: ${(err as Error).message}`); setFrameSrc(config.url) })
  }, [config?.auto_login, config?.enabled, config?.url])

  useEffect(() => { if (config?.enabled) startGuacamoleSession() }, [config?.auto_login, config?.enabled, config?.url, startGuacamoleSession])

  if (error) return <div className="remote-desktop-page"><div className="remote-card"><h2>Remote Desktop</h2><p className="remote-error">Unable to load config: {error}</p></div></div>
  if (!config) return <div className="remote-desktop-page"><div className="remote-card">Loading remote desktop status...</div></div>

  const overallStatus = config.enabled ? (remoteHealth?.ok ? 'ready' : 'degraded') : 'disabled'

  return (
    <div className="remote-desktop-page">
      <div className="remote-header">
        <div><h2>Remote Desktop</h2><p>Browser access through the remote desktop gateway.</p></div>
        <button className="btn-refresh" onClick={refresh}><RefreshCw size={14} /> Refresh</button>
      </div>
      <div className="remote-status-grid">
        <div className="remote-status-card"><span className="remote-label">Connection</span><strong className={`remote-status remote-status-${overallStatus}`}>{overallStatus}</strong></div>
        <div className="remote-status-card"><span className="remote-label">Gateway</span><strong>{remoteHealth?.guacamole || 'unknown'}</strong></div>
        <div className="remote-status-card"><span className="remote-label">RDP target</span><strong>{remoteHealth?.rdp || 'unknown'}</strong><small>{remoteHealth?.rdp_host || config.rdp_host}:{remoteHealth?.rdp_port || 3389}</small></div>
        <div className="remote-status-card"><span className="remote-label">Security</span><strong>{config.security.replace('_', ' ')}</strong></div>
      </div>
      {!config.enabled ? (
        <div className="remote-card remote-disabled"><h3>Remote desktop is disabled</h3><p>Enable the remote desktop service.</p></div>
      ) : (
        <div ref={frameShellRef} className="remote-frame-shell">
          <div className="remote-frame-toolbar">
            <div className="remote-frame-title"><span>Remote Desktop</span>{autoLoginStatus && <small>{autoLoginStatus}</small>}</div>
            <div className="remote-frame-actions">
              <button className="btn-refresh" onClick={startGuacamoleSession}><RefreshCw size={14} /> Reconnect</button>
              <button className="btn-refresh" onClick={toggleFullscreen}>{isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}{isFullscreen ? 'Exit' : 'Full Screen'}</button>
            </div>
          </div>
          {frameSrc ? <iframe title="Remote Desktop" src={frameSrc} className="remote-frame" allow="fullscreen; clipboard-read; clipboard-write" allowFullScreen /> : <div className="remote-frame-loading">Opening remote desktop...</div>}
        </div>
      )}
    </div>
  )
}

// ─── event timeline / task result ─────────────────────────────────────────────

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
              <details className="tool-output-details"><summary>{ev.data?.type === 'plan_output' ? 'Show plan' : 'Show output'}</summary><pre className="tool-output">{ev.data.output}</pre></details>
            )}
            {ev.data?.llm_prompt && <details className="tool-output-details"><summary>Show API prompt</summary><pre className="tool-output">{ev.data.llm_prompt}</pre></details>}
            {ev.event_type === 'plan_requested' && ev.data?.prompt && <details className="tool-output-details"><summary>Show prompt sent</summary><pre className="tool-output">{ev.data.prompt}</pre></details>}
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
  if (et === 'user_prompt_received') return { stage: 'Received', detail: 'Processing...', icon: '\ud83d\udce8' }
  if (et === 'routing_decision_made') return { stage: 'Routing', detail: msg.slice(0, 80), icon: '\ud83d\udee4\ufe0f' }
  if (et === 'plan_requested') return { stage: 'Planning', detail: 'Requesting plan...', icon: '\ud83e\udde0' }
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
    if (entry.events && entry.events.length > 0) {
      const progress = getProgressLabel(entry.events)
      const toolEvents = entry.events.filter((ev: any) => ev.data?.tool)
      return (
        <div className="task-result task-progress">
          <div className="progress-status">
            <span className="progress-icon">{progress.icon}</span>
            <span className="progress-stage">{progress.stage}</span>
            {progress.detail && <span className="progress-detail">{progress.detail}</span>}
            <span className="progress-count">{entry.events.length} events</span>
          </div>
          <div className="progress-bar-container"><div className="progress-bar-fill" /></div>
          <details className="progress-events-toggle">
            <summary>Show {entry.events.length} events ({toolEvents.length} tool calls)</summary>
            <div className="live-events">
              {entry.events.map((ev: any, i: number) => (
                <div key={i} className="live-event">
                  <span className="live-event-type">{ev.event_type}</span>
                  <span className="live-event-msg">{ev.data?.message || ''}</span>
                  {ev.data?.args_summary && <span className="live-event-args">{ev.data.args_summary}</span>}
                  {ev.data?.output && (ev.data?.type === 'tool_output' || ev.data?.type === 'plan_output') && <details className="tool-output-details"><summary>Show output</summary><pre className="tool-output">{ev.data.output}</pre></details>}
                </div>
              ))}
            </div>
          </details>
        </div>
      )
    }
    return <div className="task-message"><ReactMarkdown>{entry.content}</ReactMarkdown></div>
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
      {th.plan_summary && <details className="task-plan"><summary>Plan</summary><pre>{th.plan_summary}</pre></details>}
      {th.error && <div className="task-error">{th.error}</div>}
      {((th.metadata?.commands_run?.length ?? 0) > 0 || (th.metadata?.files_edited?.length ?? 0) > 0) && (
        <details className="task-output">
          <summary>Output ({th.metadata?.commands_run?.length || 0} commands, {th.metadata?.files_edited?.length || 0} files edited)</summary>
          <div className="output-details">
            {(th.metadata?.commands_run?.length ?? 0) > 0 && <div><strong>Commands:</strong><pre className="output-pre">{th.metadata!.commands_run!.join('\n')}</pre></div>}
            {(th.metadata?.files_edited?.length ?? 0) > 0 && <div><strong>Files edited:</strong><pre className="output-pre">{th.metadata!.files_edited!.join('\n')}</pre></div>}
            {th.metadata?.duration_seconds && <div className="output-meta">Duration: {th.metadata.duration_seconds.toFixed(1)}s</div>}
          </div>
        </details>
      )}
      {entry.events && entry.events.length > 0 && <details className="task-events" open><summary>Events ({entry.events.length})</summary><EventTimeline events={entry.events} /></details>}
    </div>
  )
}

// ─── folder browser / port manager ────────────────────────────────────────────

function PortManager() {
  const [services, setServices] = useState<ServiceInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [updateLoading, setUpdateLoading] = useState<Record<string, boolean>>({})
  const [updateError, setUpdateError] = useState<Record<string, string>>({})
  const [updateSuccess, setUpdateSuccess] = useState<Record<string, string>>({})
  const fetchServices = useCallback(() => { fetch(`${CONTROL_API}/services`).then(r => r.json()).then(data => setServices(data.services || [])).catch(() => {}).finally(() => setLoading(false)) }, [])
  useEffect(() => { fetchServices(); const id = setInterval(fetchServices, 5000); return () => clearInterval(id) }, [fetchServices])

  const waitForStatus = async (name: string, status: ServiceInfo['status'], attempts = 10) => {
    for (let i = 0; i < attempts; i++) { const res = await fetch(`${CONTROL_API}/services`); const data = await res.json(); setServices(data.services || []); if ((data.services || []).find((s: ServiceInfo) => s.name === name)?.status === status) return; await new Promise(r => setTimeout(r, 1000)) }
  }
  const startService = async (name: string) => { setActionLoading(`${name}:start`); try { await fetch(`${CONTROL_API}/services/${name}/start`, { method: 'POST' }); await waitForStatus(name, 'running'); if (name === 'dashboard') window.location.reload() } catch {} setActionLoading(null) }
  const stopService = async (name: string) => { setActionLoading(`${name}:stop`); try { await fetch(`${CONTROL_API}/services/${name}/stop`, { method: 'POST' }); await waitForStatus(name, 'stopped') } catch {} setActionLoading(null) }
  const updateLatest = async (name: string) => {
    setUpdateLoading(p => ({ ...p, [name]: true })); setUpdateError(p => { const n = { ...p }; delete n[name]; return n }); setUpdateSuccess(p => { const n = { ...p }; delete n[name]; return n })
    try {
      const res = await fetch(`${CONTROL_API}/v2/services/${name}/update-latest`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ restart: true }) }); const data = await res.json()
      if (data.ok && data.deferred) { setUpdateSuccess(p => ({ ...p, [name]: 'Updating...' })); for (let i = 0; i < 30; i++) { await new Promise(r => setTimeout(r, 2000)); try { const h = await fetch(`${CONTROL_API}/health`, { signal: AbortSignal.timeout(3000) }); if (h.ok) { fetchServices(); break } } catch {} } setUpdateSuccess(p => ({ ...p, [name]: 'Updated.' })); setUpdateLoading(p => ({ ...p, [name]: false })); return }
      if (data.ok) { setUpdateSuccess(p => ({ ...p, [name]: data.message || 'Updated' })) } else { setUpdateError(p => ({ ...p, [name]: data.error?.message || 'Failed' })) }
      fetchServices()
    } catch { setUpdateError(p => ({ ...p, [name]: 'Network error' })) }
    setUpdateLoading(p => ({ ...p, [name]: false }))
  }
  const restartService = async (name: string) => { setActionLoading(`${name}:restart`); try { await fetch(`${CONTROL_API}/services/${name}/restart`, { method: 'POST' }); await waitForStatus(name, 'running', name === 'control-plane' ? 15 : 10); if (name === 'dashboard' || name === 'control-plane') window.location.reload() } catch {} setActionLoading(null) }

  if (loading) return <div className="port-manager"><div className="pm-loading">Discovering services...</div></div>
  return (
    <div className="port-manager">
      <div className="pm-header"><Server size={16} /><span>Services</span><button className="pm-refresh" onClick={fetchServices} title="Refresh"><RefreshCw size={14} /></button></div>
      <div className="pm-list">
        {services.map(svc => (
          <div key={svc.name} className={`pm-item pm-${svc.status}`}>
            <div className="pm-item-info">
              <Circle size={8} fill={svc.status === 'running' ? '#4ade80' : '#94a3b8'} stroke={svc.status === 'running' ? '#4ade80' : '#94a3b8'} />
              <span className="pm-name">{svc.name}</span><span className="pm-port">:{svc.port}</span>
              {svc.docker && <span className="pm-docker">docker</span>}
            </div>
            <div className="pm-item-desc">{svc.description}</div>
            {updateError[svc.name] && <div className="pm-update-msg pm-update-error">{updateError[svc.name]}</div>}
            {updateSuccess[svc.name] && <div className="pm-update-msg pm-update-success">{updateSuccess[svc.name]}</div>}
            <div className="pm-item-actions">
              {actionLoading?.startsWith(`${svc.name}:`) ? <span className="pm-busy">...</span> : svc.status === 'running' ? (
                <>
                  {svc.can_restart !== false && <button className="pm-btn pm-btn-restart" onClick={() => restartService(svc.name)} title="Restart"><RefreshCw size={12} /></button>}
                  {svc.repo_backed && <button className={`pm-btn pm-btn-update${updateLoading[svc.name] ? ' pm-btn-updating' : ''}`} onClick={() => updateLatest(svc.name)} disabled={!svc.update_supported || updateLoading[svc.name] || svc.update_in_progress} title="Update latest"><Download size={12} className={updateLoading[svc.name] ? 'pm-spin' : ''} /></button>}
                  {svc.can_stop !== false && <button className="pm-btn pm-btn-stop" onClick={() => stopService(svc.name)} title="Stop"><Power size={12} /></button>}
                </>
              ) : (
                <>
                  {svc.can_start !== false && <button className="pm-btn pm-btn-start" onClick={() => startService(svc.name)} title="Start"><Power size={12} /></button>}
                  {svc.repo_backed && <button className={`pm-btn pm-btn-update${updateLoading[svc.name] ? ' pm-btn-updating' : ''}`} onClick={() => updateLatest(svc.name)} disabled={!svc.update_supported || updateLoading[svc.name] || svc.update_in_progress} title="Update latest"><Download size={12} className={updateLoading[svc.name] ? 'pm-spin' : ''} /></button>}
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
  const browse = useCallback((path: string) => { setLoading(true); fetch(`${API}/browse?path=${encodeURIComponent(path)}`).then(r => r.json()).then(data => { setCurrentPath(data.path || path); setEntries(data.entries || []); setParentPath(data.parent || null) }).catch(() => {}).finally(() => setLoading(false)) }, [])
  useEffect(() => { browse(currentPath) }, [])
  return (
    <div className="folder-browser">
      <div className="browser-header"><span className="browser-path">{currentPath}</span></div>
      <div className="browser-entries">
        {parentPath && currentPath !== '/' && <div className="browser-entry" onClick={() => browse(parentPath)}><ArrowUp size={16} className="entry-icon-svg" /><span className="entry-name">..</span></div>}
        {loading && <div className="browser-loading">Loading...</div>}
        {entries.map(entry => (
          <div key={entry.path} className={`browser-entry ${entry.is_repo ? 'is-repo' : ''}`} onClick={() => entry.is_repo ? onSelect(entry.path) : browse(entry.path)}>
            {entry.is_repo ? <GitBranch size={16} className="entry-icon-svg repo-icon" /> : <Folder size={16} className="entry-icon-svg" />}
            <span className="entry-name">{entry.name}</span>
            {entry.is_repo && <span className="entry-badge">repo</span>}
          </div>
        ))}
        {!loading && entries.length === 0 && <div className="browser-empty">Empty directory</div>}
      </div>
    </div>
  )
}

// ─── resizable divider ────────────────────────────────────────────────────────

function ResizeDivider({ onResize }: { onResize: (delta: number) => void }) {
  const dragging = useRef(false)
  const lastX = useRef(0)
  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault(); dragging.current = true; lastX.current = e.clientX
    document.body.style.cursor = 'col-resize'; document.body.style.userSelect = 'none'
    const onMove = (ev: MouseEvent) => { if (!dragging.current) return; onResize(ev.clientX - lastX.current); lastX.current = ev.clientX }
    const onUp = () => { dragging.current = false; document.body.style.cursor = ''; document.body.style.userSelect = ''; document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp) }
    document.addEventListener('mousemove', onMove); document.addEventListener('mouseup', onUp)
  }, [onResize])
  return <div className="resize-divider" onMouseDown={onMouseDown} />
}

// ─── main app ─────────────────────────────────────────────────────────────────

export default function App() {
  // Inject live-event styles
  if (!document.getElementById('live-event-styles')) {
    const s = document.createElement('style'); s.id = 'live-event-styles'
    s.textContent = `
.task-progress{border-left:3px solid #60a5fa}.tool-output-details{margin:4px 0}.tool-output-details summary{cursor:pointer;font-size:12px;color:#6366f1;font-weight:500;padding:2px 0;user-select:none}.tool-output-details summary:hover{color:#4f46e5}.tool-output{background:#f1f5f9;border:1px solid #e2e8f0;border-radius:6px;padding:8px 12px;margin:4px 0;font-size:12px;font-family:monospace;white-space:pre-wrap;word-break:break-all;max-height:300px;overflow-y:auto;color:#334155;line-height:1.4}.live-events{display:flex;flex-direction:column;gap:4px;padding:8px 0;max-height:300px;overflow-y:auto}.live-event{display:flex;gap:8px;align-items:baseline;font-size:12px;padding:2px 0}.live-event-type{font-family:monospace;font-size:11px;color:#6366f1;min-width:120px}.live-event-msg{color:#374151;flex:1}.live-event-args{font-family:monospace;font-size:11px;color:#6b7280;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.task-message{background:#f8fafc;padding:12px 16px;border-radius:8px;font-size:14px;line-height:1.6;color:#1e293b;overflow-x:auto;white-space:normal}.task-message h2{font-size:16px;margin:8px 0 4px;color:#1e293b}.task-message h3{font-size:14px;margin:6px 0 2px;color:#334155}.task-message p{margin:4px 0}.task-message ul,.task-message ol{margin:4px 0;padding-left:20px}.task-message li{margin:2px 0}.task-message code{background:#e2e8f0;padding:1px 4px;border-radius:3px;font-size:13px}.task-message pre{background:#1e293b;color:#e2e8f0;padding:8px 12px;border-radius:6px;overflow-x:auto}.task-message pre code{background:none;padding:0;color:inherit}.task-message strong{color:#0f172a}.task-message a{color:#6366f1;text-decoration:underline}.event-msg p{margin:0;display:inline}.event-msg h2,.event-msg h3{font-size:13px;margin:2px 0}.event-msg ul{margin:2px 0;padding-left:16px;font-size:12px}
`
    document.head.appendChild(s)
  }

  const [sessionId, setSessionId] = useState<string | null>(null)
  const [sessions, setSessions] = useState<SessionRecord[]>([])
  const [chat, setChat] = useState<ChatEntry[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [executionMode, setExecutionMode] = useState<'finite' | 'open_ended' | 'loop'>('finite')
  const [health, setHealth] = useState<Health | null>(null)
  const [newSessionRepo, setNewSessionRepo] = useState('agent-core')
  const [showBrowser, setShowBrowser] = useState(true)
  const [routePath, setRoutePath] = useState(window.location.pathname)
  const chatEndRef = useRef<HTMLDivElement>(null)

  // Sidebar state
  const [sidebarWidth, setSidebarWidth] = useState(240)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [wsDropdownOpen, setWsDropdownOpen] = useState(false)
  const [navActive, setNavActive] = useState('sessions')
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [recentMenuOpen, setRecentMenuOpen] = useState(false)
  const [sortBy, setSortBy] = useState<'created' | 'updated'>('updated')
  const [filters, setFilters] = useState({ schedules: false, archived: false, automations: false })
  const searchInputRef = useRef<HTMLInputElement>(null)

  const workspaceName = 'Current Workspace'

  const navigate = useCallback((path: string) => { window.history.pushState({}, '', path); setRoutePath(path) }, [])
  useEffect(() => { const h = () => setRoutePath(window.location.pathname); window.addEventListener('popstate', h); return () => window.removeEventListener('popstate', h) }, [])
  useEffect(() => { const f = () => fetch(`${API}/health`).then(r => r.json()).then(setHealth).catch(() => {}); f(); const id = setInterval(f, 10000); return () => clearInterval(id) }, [])
  const fetchSessions = useCallback(() => { fetch(`${API}/sessions`).then(r => r.json()).then(d => setSessions(d.sessions || [])).catch(() => {}) }, [])
  useEffect(() => { fetchSessions() }, [fetchSessions])
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [chat])
  useEffect(() => { if (searchOpen) searchInputRef.current?.focus() }, [searchOpen])

  const createSession = async () => {
    const name = `session-${Date.now().toString(36)}`
    const res = await fetch(`${API}/sessions`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, repo: newSessionRepo }) })
    const data = await res.json()
    if (data.id) { setSessionId(data.id); setChat([{ id: generateUUID(), role: 'system', content: `Session created: ${data.id}`, timestamp: new Date().toISOString() }]); fetchSessions(); navigate(`/session/${data.id}`) }
  }

  const selectSession = async (id: string) => {
    setSessionId(id)
    try { const evRes = await fetch(`${API}/sessions/${id}/events`); const evData = await evRes.json(); if (evData.events?.length > 0) { setChat([{ id: generateUUID(), role: 'system', content: `Resumed session: ${id} (${evData.total} events)`, timestamp: new Date().toISOString(), events: evData.events }]) } else { setChat([{ id: generateUUID(), role: 'system', content: `Selected session: ${id}`, timestamp: new Date().toISOString() }]) } } catch { setChat([{ id: generateUUID(), role: 'system', content: `Selected session: ${id}`, timestamp: new Date().toISOString() }]) }
  }

  const sendMessage = async () => {
    if (!input.trim() || sending || !sessionId) return
    const instruction = input.trim(); setInput(''); setSending(true)
    setChat(prev => [...prev, { id: generateUUID(), role: 'user', content: instruction, timestamp: new Date().toISOString() }])
    const progressId = generateUUID()
    setChat(prev => [...prev, { id: progressId, role: 'system', content: 'Working...', timestamp: new Date().toISOString(), events: [] }])
    let lastSeq = 0; let polling = true
    const pollEvents = async () => { while (polling) { try { const evRes = await fetch(`${API}/sessions/${sessionId}/events/stream?after=${lastSeq}`); const evData = await evRes.json(); if (evData.events?.length > 0) { lastSeq = evData.total; setChat(prev => prev.map(e => e.id === progressId ? { ...e, events: [...(e.events || []), ...evData.events], content: evData.events[evData.events.length - 1]?.data?.message || e.content } : e)) } } catch {} await new Promise(r => setTimeout(r, 800)) } }
    pollEvents()
    try {
      const res = await fetch(`${API}/sessions/${sessionId}/chat`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ instruction, execution_mode: executionMode }) })
      const taskHandle: TaskHandle = await res.json()
      if (taskHandle.state === 'working') { let done = false; while (!done) { await new Promise(r => setTimeout(r, 2000)); try { const s = await fetch(`${API}/sessions/${sessionId}/chat/status`); const d = await s.json(); if (d.state !== 'working') { done = true; Object.assign(taskHandle, d) } } catch {} } }
      polling = false
      let events: SessionEvent[] = []; try { const evRes = await fetch(`${API}/sessions/${sessionId}/events`); events = (await evRes.json()).events || [] } catch {}
      let sessionState: SessionState | undefined; try { sessionState = await (await fetch(`${API}/sessions/${sessionId}/state`)).json() } catch {}
      setChat(prev => prev.map(e => e.id === progressId ? { ...e, content: taskHandle.message || 'Done.', taskHandle, events, sessionState } : e))
    } catch (err: any) { polling = false; setChat(prev => prev.map(e => e.id === progressId ? { ...e, content: `Error: ${(err as Error).message}` } : e)) } finally { setSending(false) }
  }

  const destroySession = async (id: string) => { await fetch(`${API}/sessions/${id}`, { method: 'DELETE' }); fetchSessions(); if (sessionId === id) { setSessionId(null); setChat([]) } }

  const sortedSessions = [...sessions].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
  const filteredSessions = sortedSessions.filter(s => { if (!searchQuery) return true; const l = s.repo_path?.split('/').pop() || s.id; return l.toLowerCase().includes(searchQuery.toLowerCase()) || s.id.toLowerCase().includes(searchQuery.toLowerCase()) })

  const handleSidebarResize = useCallback((delta: number) => { setSidebarWidth(prev => Math.max(180, Math.min(400, prev + delta))) }, [])

  if (routePath === '/settings') return <SettingsPage workspaceName={workspaceName} onBack={() => navigate('/')} />

  const navItems = [
    { key: 'sessions', label: 'Sessions', icon: <Layers size={16} /> },
    { key: 'graph', label: 'Session Graph', icon: <GitBranch size={16} />, badge: 'New' },
    { key: 'ask', label: 'Ask', icon: <MessageSquare size={16} /> },
    { key: 'wiki', label: 'Knowledge', icon: <BookOpen size={16} /> },
    { key: 'review', label: 'Review', icon: <Eye size={16} /> },
    { key: 'automations', label: 'Automations', icon: <Sparkles size={16} />, badge: 'Beta' },
  ]

  return (
    <div className="app-shell">
      {/* Persistent sidebar */}
      <aside className="app-sidebar" style={{ width: sidebarCollapsed ? 52 : sidebarWidth }} aria-label="Workspace sidebar">
        {sidebarCollapsed ? (
          <>
            <button className="sidebar-expand-btn" onClick={() => setSidebarCollapsed(false)} aria-label="Expand sidebar"><ChevronRight size={16} /></button>
            <div className="sidebar-collapsed-nav">
              {navItems.map(n => <button key={n.key} className={`sidebar-icon-btn ${navActive === n.key ? 'active' : ''}`} onClick={() => { setNavActive(n.key); if (n.key === 'graph') navigate('/session-graph'); setSidebarCollapsed(false) }} title={n.label} aria-label={n.label}>{n.icon}</button>)}
            </div>
            <div className="sidebar-collapsed-footer">
              <button className="sidebar-icon-btn" onClick={() => navigate('/settings')} title="Settings" aria-label="Settings"><Settings size={16} /></button>
            </div>
          </>
        ) : (
          <>
            {/* Workspace header */}
            <div className="sidebar-ws-header">
              <button className="ws-trigger" onClick={() => setWsDropdownOpen(!wsDropdownOpen)} aria-haspopup="true" aria-expanded={wsDropdownOpen} aria-label="Workspace menu">
                <div className="ws-avatar-sm">{workspaceName.charAt(0).toUpperCase()}</div>
                <span className="ws-name-text">{workspaceName}</span>
                <ChevronDown size={14} className="ws-chevron" />
              </button>
              <button className="sidebar-collapse-btn" onClick={() => setSidebarCollapsed(true)} aria-label="Collapse sidebar"><ChevronLeft size={16} /></button>
              <WorkspaceDropdown workspaceName={workspaceName} open={wsDropdownOpen} onClose={() => setWsDropdownOpen(false)} onSettings={() => { setWsDropdownOpen(false); navigate('/settings') }} />
            </div>

            {/* Primary nav */}
            <nav className="sidebar-primary-nav" aria-label="Primary navigation">
              {navItems.map(n => (
                <button key={n.key} className={`sidebar-nav-item ${navActive === n.key ? 'active' : ''}`} onClick={() => { setNavActive(n.key); if (n.key === 'graph') navigate('/session-graph') }} aria-label={n.label}>
                  {n.icon} <span>{n.label}</span>
                  {n.badge && <span className="sidebar-badge">{n.badge}</span>}
                </button>
              ))}
            </nav>

            {/* Recent sessions */}
            <div className="sidebar-recent">
              {searchOpen ? (
                <div className="sidebar-search-bar">
                  <Search size={12} />
                  <input ref={searchInputRef} className="sidebar-search-input" placeholder="Search sessions..." value={searchQuery} onChange={e => setSearchQuery(e.target.value)} onKeyDown={e => { if (e.key === 'Escape') { setSearchOpen(false); setSearchQuery('') } }} aria-label="Search sessions" />
                  <button className="sidebar-search-close" onClick={() => { setSearchOpen(false); setSearchQuery('') }} aria-label="Close search"><X size={12} /></button>
                </div>
              ) : (
                <div className="sidebar-recent-header">
                  <span className="sidebar-recent-label">Recent</span>
                  <div className="sidebar-recent-actions">
                    <button className="sidebar-icon-btn" onClick={() => setSearchOpen(true)} title="Search sessions" aria-label="Search sessions"><Search size={14} /></button>
                    <button className="sidebar-icon-btn" onClick={createSession} title="New session" aria-label="New session"><Plus size={14} /></button>
                    <button className="sidebar-icon-btn" onClick={() => setRecentMenuOpen(!recentMenuOpen)} title="More options" aria-label="More options" aria-haspopup="true" aria-expanded={recentMenuOpen}><MoreHorizontal size={14} /></button>
                  </div>
                  <RecentMenu open={recentMenuOpen} onClose={() => setRecentMenuOpen(false)} sortBy={sortBy} onSortChange={v => { setSortBy(v); setRecentMenuOpen(false) }} filters={filters} onFilterToggle={k => setFilters(p => ({ ...p, [k]: !p[k] }))} />
                </div>
              )}
              <div className="sidebar-session-list">
                {filteredSessions.map(s => {
                  const label = s.repo_path?.split('/').pop() || s.id
                  const isActive = routePath === `/session/${s.id}`
                  const isLive = s.status === 'running'
                  return (
                    <div key={s.id} className={`sidebar-session-row ${isActive ? 'active' : ''}`} onClick={() => navigate(`/session/${s.id}`)} role="button" tabIndex={0} aria-label={`Session: ${label}`}>
                      <div className="sidebar-session-top">
                        <span className="sidebar-session-name">{truncStr(label, 24)}</span>
                        {isLive && <span className="sidebar-live-dot" />}
                        <button className="sidebar-session-destroy" onClick={e => { e.stopPropagation(); destroySession(s.id) }} title="Delete session" aria-label="Delete session"><X size={12} /></button>
                      </div>
                      <div className="sidebar-session-meta">
                        <span>{relativeTime(s.created_at)}</span>
                        {s.repo_path && <span className="sidebar-session-repo"><GitBranch size={10} /> {s.repo_path.split('/').pop()}</span>}
                      </div>
                    </div>
                  )
                })}
                {filteredSessions.length === 0 && <div className="sidebar-empty">No sessions found.</div>}
              </div>
            </div>

            {/* Footer */}
            <div className="sidebar-footer">
              <button className="sidebar-nav-item" onClick={() => navigate('/settings')} aria-label="Settings"><Settings size={16} /> <span>Settings</span></button>
              <button className="sidebar-icon-btn" title="Help" aria-label="Help"><HelpCircle size={16} /></button>
            </div>
          </>
        )}
      </aside>

      {!sidebarCollapsed && <ResizeDivider onResize={handleSidebarResize} />}

      {/* Main content */}
      <main className="app-main">
        {routePath.startsWith('/session/') ? (
          <AgentSessionPage sessionId={routePath.replace('/session/', '')} onBack={() => navigate('/')} sessions={sessions} onNavigateSession={id => navigate(`/session/${id}`)} />
        ) : routePath === '/remote-desktop' ? (
          <RemoteDesktopPage />
        ) : routePath === '/session-graph' ? (
          <SessionGraphExplorer />
        ) : !sessionId ? (
          <div className="welcome">
            <h2>Agent Workspace</h2>
            <p>Create or select a session to start working.</p>
            <div className="welcome-actions">
              <div className="repo-input-row">
                <input className="repo-input" value={newSessionRepo} onChange={e => setNewSessionRepo(e.target.value)} placeholder="Repo name or path..." />
                <button className="btn-browse" onClick={() => setShowBrowser(!showBrowser)}><Folder size={14} />{showBrowser ? 'Close' : 'Browse...'}</button>
              </div>
              <button className="btn-start" onClick={createSession}>Start Session</button>
            </div>
            {showBrowser && <FolderBrowser onSelect={path => { setNewSessionRepo(path); setShowBrowser(false) }} />}
            <PortManager />
          </div>
        ) : (
          <div className="chat-area">
            <div className="chat-messages">
              {chat.map(entry => (
                <div key={entry.id} className={`chat-entry chat-${entry.role}`}>
                  {entry.role === 'user' ? <div className="msg-bubble user-bubble"><div className="msg-text">{entry.content}</div></div> : <div className="msg-bubble system-bubble"><TaskResult entry={entry} /></div>}
                </div>
              ))}
              <div ref={chatEndRef} />
            </div>
            <div className="chat-input-area">
              <div className="mode-selector">
                {(['finite', 'open_ended', 'loop'] as const).map(mode => (
                  <button key={mode} className={`mode-btn ${executionMode === mode ? 'mode-active' : ''}`} onClick={() => setExecutionMode(mode)} disabled={sending} title={mode === 'finite' ? 'Limited iterations' : mode === 'open_ended' ? 'No limit' : 'Continuous loop'}>
                    {mode === 'finite' ? '\u23f1 Finite' : mode === 'open_ended' ? '\u267e Open' : '\ud83d\udd01 Loop'}
                  </button>
                ))}
              </div>
              <div className="input-wrapper">
                <input className="chat-input" value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && !e.shiftKey && sendMessage()} placeholder="Ask the agent to build features, fix bugs, or work on your code" disabled={sending} autoFocus />
                <button className="btn-send" onClick={sendMessage} disabled={sending || !input.trim()}><Send size={20} /></button>
              </div>
              <div className="input-meta">Session: <strong>{sessionId}</strong> | Press Enter to send</div>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
