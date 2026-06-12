import { useState, useEffect, useRef, useCallback, type ReactNode } from 'react'
import {
  ChevronLeft, ChevronRight, ChevronDown, Folder, GitBranch, Plus, X, Circle,
  ArrowUp, Power, RefreshCw, Server, Monitor, Maximize2,
  Minimize2, Download, Search, MoreHorizontal, Settings, HelpCircle,
  BookOpen, Check, Filter, SortAsc, Archive, Zap, Shield, Key,
  BarChart3, Terminal, Cpu,
} from 'lucide-react'
import AgentSessionPage from './AgentSessionPage'
import SessionGraphExplorer from './components/session-graph/SessionGraphExplorer'
import './agent-session.css'

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

function statusTone(status?: string | boolean): 'ok' | 'warn' | 'bad' | 'neutral' {
  if (status === true) return 'ok'
  if (status === false) return 'bad'
  const s = String(status || '').toLowerCase()
  if (['healthy', 'running', 'reachable', 'ready', 'ok', 'enabled'].includes(s)) return 'ok'
  if (['degraded', 'unknown', 'not_configured', 'partial'].includes(s)) return 'warn'
  if (['unhealthy', 'stopped', 'unreachable', 'disabled', 'failed', 'error'].includes(s)) return 'bad'
  return 'neutral'
}

interface Health {
  agent_core?: { status: string; url?: string; error?: string }
  litellm?: { status: string; url?: string; error?: string }
  vendor_runtime?: { status: string; url?: string; error?: string }
  bridge?: { status: string; url?: string; error?: string }
  disk?: { used?: string; available?: string; percent?: string }
  memory?: { total?: string; used?: string; available?: string }
  cpu?: { load_1m?: string; load_5m?: string; load_15m?: string }
  active_ports?: number[]
  docker?: Array<{ name: string; status: string; ports?: string }>
}

interface RemoteDesktopConfig { enabled: boolean; provider: string; url: string; rdp_host: string; security: string; auto_login: boolean }
interface RemoteDesktopHealth { ok: boolean; enabled: boolean; provider: string; guacamole: string; guacd: string; rdp: string; rdp_host: string; rdp_port: number; guacamole_url?: string; details?: Record<string, unknown> }
interface SessionRecord { id: string; status: string; repo_path: string; created_at: string }
interface BrowseEntry { name: string; path: string; is_dir: boolean; is_repo: boolean }
interface ServiceInfo {
  name: string; port: number; description: string; status: 'running' | 'stopped'; pid: number | null
  docker?: boolean; repo_backed?: boolean; update_supported?: boolean; update_in_progress?: boolean
  last_update?: { commit: string; timestamp: string; status: string } | null
  can_start?: boolean; can_stop?: boolean; can_restart?: boolean
}
interface GuacamoleSession { authToken: string; username: string; dataSource: string; availableDataSources: string[]; connection_url: string }
interface ModelInfo { id?: string; model_name?: string; litellm_params?: Record<string, any>; object?: string; [key: string]: any }
interface KnowledgeEntry { id?: string; title?: string; name?: string; description?: string; content?: string; [key: string]: any }

type LoggingExtent = 'minimal' | 'standard' | 'verbose' | 'diagnostic'
interface ObservabilitySettings {
  logging_extent: LoggingExtent
  lookback_hours: number
  include_ambient_context: boolean
  include_debug_prompts: boolean
  include_tool_outputs: boolean
  max_events_per_session: number
}

const API = '/api'
const CONTROL_API = window.location.port === '5173'
  ? `${window.location.protocol}//${window.location.hostname}:9877/api`
  : API

function endpoint(path: string): string {
  return `${CONTROL_API}${path.startsWith('/') ? path : `/${path}`}`
}

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(endpoint(path))
  if (!res.ok) throw new Error(await res.text() || `${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

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

function useEndpoint<T>(path: string, initial: T, intervalMs?: number) {
  const [data, setData] = useState<T>(initial)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const refresh = useCallback(async () => {
    setError('')
    try { setData(await fetchJson<T>(path)) }
    catch (err) { setError((err as Error).message) }
    finally { setLoading(false) }
  }, [path])
  useEffect(() => {
    refresh()
    if (!intervalMs) return undefined
    const id = setInterval(refresh, intervalMs)
    return () => clearInterval(id)
  }, [refresh, intervalMs])
  return { data, loading, error, refresh }
}

function StatusPill({ value }: { value?: string | boolean }) {
  const text = typeof value === 'boolean' ? (value ? 'enabled' : 'disabled') : (value || 'unknown')
  return <span className={`settings-status-pill settings-status-${statusTone(value)}`}>{text}</span>
}

function SettingCard({ title, description, children, action }: { title: string; description?: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <section className="settings-detail-card">
      <div className="settings-detail-card-head">
        <div>
          <h3>{title}</h3>
          {description && <p>{description}</p>}
        </div>
        {action}
      </div>
      {children && <div className="settings-detail-body">{children}</div>}
    </section>
  )
}

function InfoRows({ rows }: { rows: Array<{ label: string; value: ReactNode }> }) {
  return <div className="settings-info-rows">{rows.map(row => <div key={row.label} className="settings-info-row"><span>{row.label}</span><strong>{row.value}</strong></div>)}</div>
}

function EndpointBadge({ children }: { children: ReactNode }) {
  return <code className="settings-endpoint">{children}</code>
}

function SettingsStyles() {
  useEffect(() => {
    if (document.getElementById('settings-runtime-styles')) return
    const s = document.createElement('style')
    s.id = 'settings-runtime-styles'
    s.textContent = `
.settings-page{display:flex;height:100vh;background:#f8fafc;color:#0f172a}.settings-sidebar{width:280px;flex-shrink:0;border-right:1px solid #e2e8f0;background:#fff;padding:18px;overflow:auto}.settings-back{display:inline-flex;align-items:center;gap:6px;border:1px solid #e2e8f0;background:#fff;border-radius:8px;padding:7px 10px;font-size:13px;cursor:pointer}.settings-search-wrap{display:flex;align-items:center;gap:8px;border:1px solid #e2e8f0;border-radius:10px;padding:8px 10px;margin:16px 0}.settings-search{border:0;outline:0;background:transparent;flex:1;font-size:13px}.settings-nav-section{margin:16px 0}.settings-nav-label{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:#64748b;margin:0 0 7px}.settings-nav-item{width:100%;display:flex;align-items:center;justify-content:space-between;text-align:left;border:0;background:transparent;border-radius:8px;padding:8px 10px;color:#334155;cursor:pointer;font-size:13px}.settings-nav-item:hover,.settings-nav-item.active{background:#eef2ff;color:#3730a3}.settings-badge{font-size:10px;border:1px solid #c7d2fe;background:#eef2ff;color:#3730a3;border-radius:999px;padding:1px 6px}.settings-main{flex:1;overflow:auto}.settings-content{max-width:1100px;margin:0 auto;padding:34px}.settings-title{font-size:28px;margin:0}.settings-subtitle{margin:6px 0 24px;color:#64748b}.settings-layout{display:grid;grid-template-columns:320px minmax(0,1fr);gap:22px}.settings-group{margin-bottom:20px}.settings-group-label{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:#64748b;margin:0 0 8px}.settings-card,.settings-detail-card{background:#fff;border:1px solid #e2e8f0;border-radius:14px;box-shadow:0 1px 2px rgba(15,23,42,.04)}.settings-row{width:100%;display:flex;align-items:center;gap:10px;border:0;background:transparent;border-bottom:1px solid #f1f5f9;padding:13px 14px;text-align:left;cursor:pointer}.settings-row:last-child{border-bottom:0}.settings-row:hover,.settings-row.active{background:#f8fafc}.settings-row-icon{width:28px;height:28px;border-radius:8px;background:#f1f5f9;color:#475569;display:flex;align-items:center;justify-content:center}.settings-row-label{font-weight:600;font-size:13px;flex:1}.settings-row-description{display:block;font-size:12px;color:#64748b;margin-top:2px}.settings-row-chevron{color:#94a3b8}.settings-detail-card{margin-bottom:16px;padding:18px}.settings-detail-card-head{display:flex;justify-content:space-between;gap:14px;align-items:flex-start}.settings-detail-card h3{font-size:16px;margin:0 0 4px}.settings-detail-card p{margin:0;color:#64748b;font-size:13px;line-height:1.5}.settings-detail-body{margin-top:14px}.settings-info-rows{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px}.settings-info-row{border:1px solid #e2e8f0;border-radius:10px;padding:10px 12px;background:#f8fafc}.settings-info-row span{display:block;font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:.04em}.settings-info-row strong{display:block;margin-top:3px;font-size:13px;word-break:break-word}.settings-status-pill{display:inline-flex;align-items:center;border-radius:999px;padding:2px 8px;font-size:11px;font-weight:700;text-transform:uppercase}.settings-status-ok{background:#dcfce7;color:#166534}.settings-status-warn{background:#fef3c7;color:#92400e}.settings-status-bad{background:#fee2e2;color:#991b1b}.settings-status-neutral{background:#e2e8f0;color:#334155}.settings-endpoint{font-size:12px;background:#f1f5f9;border:1px solid #e2e8f0;border-radius:6px;padding:2px 6px;color:#334155}.settings-table{width:100%;border-collapse:collapse;font-size:13px}.settings-table th{text-align:left;color:#64748b;font-size:11px;text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid #e2e8f0;padding:8px}.settings-table td{border-bottom:1px solid #f1f5f9;padding:10px 8px;vertical-align:top}.settings-btn{display:inline-flex;align-items:center;gap:6px;border:1px solid #cbd5e1;background:#fff;border-radius:8px;padding:7px 10px;font-size:12px;cursor:pointer;color:#0f172a}.settings-btn:hover{background:#f8fafc}.settings-btn:disabled{opacity:.5;cursor:not-allowed}.settings-btn-primary{background:#4f46e5;border-color:#4f46e5;color:#fff}.settings-muted{color:#64748b;font-size:13px}.settings-error{border:1px solid #fecaca;background:#fef2f2;color:#991b1b;border-radius:10px;padding:10px 12px;font-size:13px}.settings-empty{border:1px dashed #cbd5e1;border-radius:10px;padding:18px;color:#64748b;text-align:center;font-size:13px}.settings-list{display:flex;flex-direction:column;gap:8px}.settings-list-item{display:flex;justify-content:space-between;gap:12px;border:1px solid #e2e8f0;border-radius:10px;padding:10px 12px;background:#f8fafc}.settings-list-title{font-weight:700;font-size:13px}.settings-list-sub{display:block;font-size:12px;color:#64748b;margin-top:2px}.settings-warning{border:1px solid #fde68a;background:#fffbeb;color:#92400e;border-radius:10px;padding:10px 12px;font-size:13px;line-height:1.5}.settings-field{display:flex;flex-direction:column;gap:6px}.settings-field span{font-size:12px;font-weight:700;color:#334155}.settings-field small{font-size:12px;color:#64748b}.settings-field select,.settings-field input{border:1px solid #cbd5e1;border-radius:8px;padding:8px}.settings-control-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}.settings-toggle-list{display:flex;flex-direction:column;gap:8px;margin-top:12px}.settings-actions{display:flex;align-items:center;gap:10px;margin-top:14px}@media(max-width:900px){.settings-layout{grid-template-columns:1fr}.settings-sidebar{width:230px}.settings-content{padding:22px}}
`
    document.head.appendChild(s)
  }, [])
  return null
}

function WorkspaceDropdown({ workspaceName, open, onClose, onSettings }: { workspaceName: string; open: boolean; onClose: () => void; onSettings: () => void }) {
  const ref = useRef<HTMLDivElement>(null)
  useClickOutside(ref, onClose)
  useEscapeKey(onClose, open)
  if (!open) return null
  return (
    <div className="ws-dropdown" ref={ref} role="menu" aria-label="Workspace menu">
      <div className="ws-dropdown-header">
        <div className="ws-dropdown-identity"><div className="ws-avatar">{workspaceName.charAt(0).toUpperCase()}</div><div className="ws-identity-text"><span className="ws-identity-name">{workspaceName}</span><span className="ws-identity-sub">Organization</span></div></div>
        <div className="ws-dropdown-header-actions"><button className="ws-btn-sm" onClick={onSettings} aria-label="Settings"><Settings size={14} /> Settings</button></div>
      </div>
      <div className="ws-dropdown-section"><span className="ws-section-label">Team &amp; Personal</span></div>
      <div className="ws-dropdown-rows"><div className="ws-workspace-row active" role="menuitem"><div className="ws-row-avatar">{workspaceName.charAt(0).toUpperCase()}</div><span className="ws-row-name">{workspaceName}</span><Check size={14} className="ws-check" /></div></div>
      <div className="ws-dropdown-footer"><button className="ws-footer-btn" role="menuitem" aria-label="Create new workspace" disabled><Plus size={14} /> Create workspace</button><button className="ws-footer-btn ws-logout" role="menuitem" aria-label="Log out" disabled>Log out</button></div>
    </div>
  )
}

function RecentMenu({ open, onClose, sortBy, onSortChange, filters, onFilterToggle }: { open: boolean; onClose: () => void; sortBy: 'created' | 'updated'; onSortChange: (v: 'created' | 'updated') => void; filters: { schedules: boolean; archived: boolean; automations: boolean }; onFilterToggle: (key: 'schedules' | 'archived' | 'automations') => void }) {
  const ref = useRef<HTMLDivElement>(null)
  useClickOutside(ref, onClose)
  useEscapeKey(onClose, open)
  if (!open) return null
  return <div className="recent-menu" ref={ref} role="menu" aria-label="Session options"><div className="recent-menu-section"><span className="recent-menu-label"><SortAsc size={12} /> Sort by</span><button className="recent-menu-item" onClick={() => onSortChange('created')} role="menuitemradio" aria-checked={sortBy === 'created'}>Created time {sortBy === 'created' && <Check size={12} />}</button><button className="recent-menu-item" onClick={() => onSortChange('updated')} role="menuitemradio" aria-checked={sortBy === 'updated'}>Last updated {sortBy === 'updated' && <Check size={12} />}</button></div><div className="recent-menu-section"><span className="recent-menu-label"><Filter size={12} /> Filter</span><label className="recent-menu-toggle"><input type="checkbox" checked={filters.schedules} onChange={() => onFilterToggle('schedules')} /><span>Schedules</span></label><label className="recent-menu-toggle"><input type="checkbox" checked={filters.archived} onChange={() => onFilterToggle('archived')} /><span>Archived</span></label><label className="recent-menu-toggle"><input type="checkbox" checked={filters.automations} onChange={() => onFilterToggle('automations')} /><span>Automations</span></label></div><div className="recent-menu-section recent-menu-actions"><button className="recent-menu-item" role="menuitem"><Archive size={12} /> Session filters only</button></div></div>
}

type SettingsKey = 'preferences' | 'general' | 'connections' | 'sessions' | 'observability' | 'usage' | 'agent' | 'knowledge' | 'remote-desktop' | 'skills' | 'environment' | 'repositories' | 'api'
type SettingsItem = { key: SettingsKey; label: string; description: string; icon: ReactNode; badge?: string }
const SETTINGS_GROUPS: Array<{ label: string; items: SettingsItem[] }> = [
  { label: 'Personal', items: [{ key: 'preferences', label: 'Preferences', description: 'Browser-local display and execution defaults.', icon: <Settings size={16} /> }] },
  { label: 'Organization', items: [
    { key: 'general', label: 'General', description: 'Workspace identity and control-plane health.', icon: <Settings size={16} /> },
    { key: 'connections', label: 'Connections', description: 'Service connectivity checks.', icon: <Zap size={16} /> },
    { key: 'sessions', label: 'Sessions', description: 'Session records from the control plane.', icon: <Layers size={16} /> },
    { key: 'observability', label: 'Observability', description: 'Logging extent and lookback period.', icon: <BarChart3 size={16} />, badge: 'Live' },
    { key: 'usage', label: 'Usage & limits', description: 'Current disk, memory, CPU, and port usage.', icon: <BarChart3 size={16} /> },
  ] },
  { label: 'Products', items: [
    { key: 'agent', label: 'Agent', description: 'Models and executor service status.', icon: <Cpu size={16} /> },
    { key: 'knowledge', label: 'Knowledge', description: 'Knowledge entries and proposed triggers.', icon: <BookOpen size={16} /> },
    { key: 'remote-desktop', label: 'Remote Desktop', description: 'Guacamole and Tailscale RDP status.', icon: <Monitor size={16} />, badge: 'Live' },
  ] },
  { label: 'Resources', items: [
    { key: 'skills', label: 'Skills & Rules', description: 'Backed by knowledge and proposed trigger endpoints.', icon: <Shield size={16} /> },
    { key: 'environment', label: 'Environment', description: 'Service manager endpoints.', icon: <Terminal size={16} /> },
  ] },
  { label: 'Administration', items: [
    { key: 'repositories', label: 'Repositories', description: 'Repo paths from sessions and safe browse.', icon: <GitBranch size={16} /> },
    { key: 'api', label: 'API', description: 'Endpoint inventory used by settings.', icon: <Key size={16} /> },
  ] },
]

const DEFAULT_OBSERVABILITY_SETTINGS: ObservabilitySettings = { logging_extent: 'standard', lookback_hours: 24, include_ambient_context: true, include_debug_prompts: false, include_tool_outputs: true, max_events_per_session: 1000 }
const LOOKBACK_OPTIONS = [{ value: 1, label: '1 hour' }, { value: 6, label: '6 hours' }, { value: 12, label: '12 hours' }, { value: 24, label: '24 hours' }, { value: 72, label: '3 days' }, { value: 168, label: '7 days' }, { value: 720, label: '30 days' }]

/* Future-only settings intentionally not rendered until backed endpoints exist: plans, invoices, review configuration, schedules, playbooks, secrets, membership, organization analytics, workspace creation, and auth/logout. */

function ObservabilitySettingsPanel() {
  const [settings, setSettings] = useState<ObservabilitySettings>(DEFAULT_OBSERVABILITY_SETTINGS)
  const [status, setStatus] = useState('Loading settings...')
  const [saving, setSaving] = useState(false)
  const load = useCallback(() => { setStatus('Loading settings...'); fetch(endpoint('/session-graph/settings/observability')).then(r => r.json()).then(data => { setSettings({ ...DEFAULT_OBSERVABILITY_SETTINGS, ...(data.settings || {}) }); setStatus('') }).catch(err => setStatus(`Unable to load settings: ${(err as Error).message}`)) }, [])
  useEffect(() => { load() }, [load])
  const save = async () => { setSaving(true); setStatus('Saving...'); try { const res = await fetch(endpoint('/session-graph/settings/observability'), { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(settings) }); if (!res.ok) throw new Error(await res.text()); const data = await res.json(); setSettings({ ...DEFAULT_OBSERVABILITY_SETTINGS, ...(data.settings || {}) }); setStatus('Saved') } catch (err) { setStatus(`Save failed: ${(err as Error).message}`) } finally { setSaving(false) } }
  const setBool = (key: keyof ObservabilitySettings) => (value: boolean) => setSettings(prev => ({ ...prev, [key]: value }))
  return <SettingCard title="Observability" description="Backed by GET/PUT /api/session-graph/settings/observability." action={<button className="settings-btn" onClick={load} disabled={saving}><RefreshCw size={14} /> Reload</button>}><div className="settings-control-grid"><label className="settings-field"><span>Logging extent</span><select value={settings.logging_extent} onChange={e => setSettings(prev => ({ ...prev, logging_extent: e.target.value as LoggingExtent }))}><option value="minimal">Minimal</option><option value="standard">Standard</option><option value="verbose">Verbose</option><option value="diagnostic">Diagnostic</option></select><small>Controls how much event, tool, ambient, and debug detail the platform records.</small></label><label className="settings-field"><span>Lookback period</span><select value={settings.lookback_hours} onChange={e => setSettings(prev => ({ ...prev, lookback_hours: Number(e.target.value) }))}>{LOOKBACK_OPTIONS.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}</select><small>Controls how far back UI timelines and context retrieval should look.</small></label><label className="settings-field"><span>Max events per session</span><input type="number" min={100} max={50000} step={100} value={settings.max_events_per_session} onChange={e => setSettings(prev => ({ ...prev, max_events_per_session: Number(e.target.value) }))} /><small>Caps the event window used for settings-aware views.</small></label></div><div className="settings-toggle-list"><label><input type="checkbox" checked={settings.include_ambient_context} onChange={e => setBool('include_ambient_context')(e.target.checked)} /> Include ambient context events</label><label><input type="checkbox" checked={settings.include_tool_outputs} onChange={e => setBool('include_tool_outputs')(e.target.checked)} /> Include tool output bodies</label><label><input type="checkbox" checked={settings.include_debug_prompts} onChange={e => setBool('include_debug_prompts')(e.target.checked)} /> Include debug LLM prompts</label></div><div className="settings-actions"><button className="settings-btn settings-btn-primary" onClick={save} disabled={saving}>{saving ? 'Saving...' : 'Save settings'}</button>{status && <span className="settings-muted">{status}</span>}</div></SettingCard>
}

function SettingsPage({ workspaceName, onBack, onNavigate }: { workspaceName: string; onBack: () => void; onNavigate: (path: string) => void }) {
  SettingsStyles()
  const [search, setSearch] = useState('')
  const [activeKey, setActiveKey] = useState<SettingsKey>('observability')
  const [compactMode, setCompactMode] = useState(() => localStorage.getItem('settings.compactMode') === 'true')
  const [defaultExecutionMode, setDefaultExecutionMode] = useState(() => localStorage.getItem('settings.defaultExecutionMode') || 'finite')
  const health = useEndpoint<Health>('/health', {}, 10000)
  const sessions = useEndpoint<{ sessions: SessionRecord[] }>('/sessions', { sessions: [] }, 10000)
  const services = useEndpoint<{ services: ServiceInfo[] }>('/services', { services: [] }, 10000)
  const models = useEndpoint<{ live: ModelInfo[]; configured: ModelInfo[] }>('/models', { live: [], configured: [] })
  const knowledge = useEndpoint<{ entries: KnowledgeEntry[] }>('/knowledge', { entries: [] })
  const proposed = useEndpoint<{ triggers: KnowledgeEntry[] }>('/knowledge/proposed', { triggers: [] })
  const remoteConfig = useEndpoint<RemoteDesktopConfig | null>('/v2/remote-desktop/config', null, 10000)
  const remoteHealth = useEndpoint<RemoteDesktopHealth | null>('/v2/remote-desktop/health', null, 10000)
  const browse = useEndpoint<{ entries: BrowseEntry[]; path?: string; error?: string }>('/browse?path=%2Fopt%2Fworkstation%2Frepos', { entries: [] })
  const refreshAll = () => { health.refresh(); sessions.refresh(); services.refresh(); models.refresh(); knowledge.refresh(); proposed.refresh(); remoteConfig.refresh(); remoteHealth.refresh(); browse.refresh() }
  const allItems = SETTINGS_GROUPS.flatMap(g => g.items)
  const activeItem = allItems.find(it => it.key === activeKey) || allItems[0]
  const filteredGroups = SETTINGS_GROUPS.map(g => ({ ...g, items: g.items.filter(it => `${it.label} ${it.description}`.toLowerCase().includes(search.toLowerCase())) })).filter(g => g.items.length > 0)
  const saveDefaultExecutionMode = (mode: string) => { setDefaultExecutionMode(mode); localStorage.setItem('settings.defaultExecutionMode', mode) }
  const saveCompactMode = (value: boolean) => { setCompactMode(value); localStorage.setItem('settings.compactMode', String(value)) }
  const renderPanel = () => {
    switch (activeKey) {
      case 'preferences': return <PreferencesSettings compactMode={compactMode} setCompactMode={saveCompactMode} defaultExecutionMode={defaultExecutionMode} setDefaultExecutionMode={saveDefaultExecutionMode} />
      case 'general': return <GeneralSettings workspaceName={workspaceName} health={health.data} error={health.error} onRefresh={health.refresh} />
      case 'connections': return <ConnectionsSettings health={health.data} services={services.data.services} error={health.error || services.error} onRefresh={() => { health.refresh(); services.refresh() }} />
      case 'sessions': return <SessionsSettings sessions={sessions.data.sessions} error={sessions.error} onRefresh={sessions.refresh} onNavigate={onNavigate} />
      case 'observability': return <ObservabilitySettingsPanel />
      case 'usage': return <UsageSettings health={health.data} error={health.error} onRefresh={health.refresh} />
      case 'agent': return <AgentSettings models={models.data} services={services.data.services} error={models.error || services.error} onRefresh={() => { models.refresh(); services.refresh() }} />
      case 'knowledge': return <KnowledgeSettings entries={knowledge.data.entries} proposed={proposed.data.triggers} error={knowledge.error || proposed.error} onRefresh={() => { knowledge.refresh(); proposed.refresh() }} />
      case 'remote-desktop': return <RemoteDesktopSettings config={remoteConfig.data} health={remoteHealth.data} error={remoteConfig.error || remoteHealth.error} onRefresh={() => { remoteConfig.refresh(); remoteHealth.refresh() }} onOpen={() => onNavigate('/remote-desktop')} />
      case 'skills': return <SkillsSettings entries={knowledge.data.entries} proposed={proposed.data.triggers} error={knowledge.error || proposed.error} onRefresh={() => { knowledge.refresh(); proposed.refresh() }} />
      case 'environment': return <EnvironmentSettings services={services.data.services} error={services.error} onRefresh={services.refresh} />
      case 'repositories': return <RepositoriesSettings sessions={sessions.data.sessions} browse={browse.data} error={sessions.error || browse.error} onRefresh={() => { sessions.refresh(); browse.refresh() }} />
      case 'api': return <ApiSettings health={health.data} />
      default: return null
    }
  }
  return <div className="settings-page"><aside className="settings-sidebar"><button className="settings-back" onClick={onBack} aria-label="Back to app"><ChevronLeft size={14} /> Back to app</button><div className="settings-search-wrap"><Search size={12} /><input className="settings-search" placeholder="Search settings..." value={search} onChange={e => setSearch(e.target.value)} aria-label="Search settings" /></div><nav className="settings-nav" aria-label="Settings navigation">{filteredGroups.map(group => <div key={group.label} className="settings-nav-section"><span className="settings-nav-label">{group.label}</span>{group.items.map(it => <button key={it.key} className={`settings-nav-item ${activeKey === it.key ? 'active' : ''}`} onClick={() => setActiveKey(it.key)}><span>{it.label}</span>{it.badge && <span className="settings-badge">{it.badge}</span>}</button>)}</div>)}</nav></aside><main className="settings-main"><div className="settings-content"><div className="settings-detail-card-head" style={{ marginBottom: 18 }}><div><h1 className="settings-title">{workspaceName}</h1><p className="settings-subtitle">Settings backed by live control-plane endpoints. Future-only surfaces are hidden until the API exists.</p></div><button className="settings-btn" onClick={refreshAll}><RefreshCw size={14} /> Refresh all</button></div><div className="settings-layout"><div>{filteredGroups.map(g => <div key={g.label} className="settings-group"><h3 className="settings-group-label">{g.label}</h3><div className="settings-card">{g.items.map(it => <button key={it.key} className={`settings-row ${activeKey === it.key ? 'active' : ''}`} onClick={() => setActiveKey(it.key)} aria-label={it.label}><div className="settings-row-icon">{it.icon}</div><span style={{ flex: 1 }}><span className="settings-row-label">{it.label}</span><span className="settings-row-description">{it.description}</span></span>{it.badge && <span className="settings-badge">{it.badge}</span>}<ChevronRight size={14} className="settings-row-chevron" /></button>)}</div></div>)}</div><div><SettingCard title={activeItem.label} description={activeItem.description}><div className="settings-warning">Only settings with a concrete backing endpoint or browser-local storage are shown. Billing, membership, secrets, schedules, playbooks, and analytics are intentionally hidden until their endpoints exist.</div></SettingCard>{renderPanel()}</div></div></div></main></div>
}

function PreferencesSettings({ compactMode, setCompactMode, defaultExecutionMode, setDefaultExecutionMode }: { compactMode: boolean; setCompactMode: (v: boolean) => void; defaultExecutionMode: string; setDefaultExecutionMode: (v: string) => void }) {
  return <><SettingCard title="Display density" description="Stored in browser localStorage. No server endpoint is required."><label className="settings-list-item"><span><span className="settings-list-title">Compact settings layout</span><span className="settings-list-sub">Reduces vertical spacing in browser-local UI state.</span></span><input type="checkbox" checked={compactMode} onChange={e => setCompactMode(e.target.checked)} /></label></SettingCard><SettingCard title="Default execution mode" description="Stored locally for the prompt composer default."><select className="repo-input" value={defaultExecutionMode} onChange={e => setDefaultExecutionMode(e.target.value)}><option value="finite">finite</option><option value="open_ended">open_ended</option><option value="loop">loop</option></select></SettingCard></>
}

function GeneralSettings({ workspaceName, health, error, onRefresh }: { workspaceName: string; health: Health; error: string; onRefresh: () => void }) {
  return <SettingCard title="Workspace summary" description="Backed by GET /api/health." action={<button className="settings-btn" onClick={onRefresh}><RefreshCw size={14} /> Refresh</button>}>{error && <div className="settings-error">{error}</div>}<InfoRows rows={[{ label: 'Workspace', value: workspaceName }, { label: 'Agent core', value: <StatusPill value={health.agent_core?.status} /> }, { label: 'LiteLLM', value: <StatusPill value={health.litellm?.status} /> }, { label: 'Bridge', value: <StatusPill value={health.bridge?.status} /> }]} /></SettingCard>
}

function ConnectionsSettings({ health, services, error, onRefresh }: { health: Health; services: ServiceInfo[]; error: string; onRefresh: () => void }) {
  const checks = [{ name: 'agent-core', status: health.agent_core?.status, detail: health.agent_core?.url || health.agent_core?.error, endpoint: '/api/health' }, { name: 'litellm', status: health.litellm?.status, detail: health.litellm?.url || health.litellm?.error, endpoint: '/api/health' }, { name: 'vendor-runtime', status: health.vendor_runtime?.status, detail: health.vendor_runtime?.url || health.vendor_runtime?.error, endpoint: '/api/health' }, { name: 'bridge', status: health.bridge?.status, detail: health.bridge?.url || health.bridge?.error, endpoint: '/api/health' }]
  return <SettingCard title="Live connections" description="Backed by GET /api/health and GET /api/services." action={<button className="settings-btn" onClick={onRefresh}><RefreshCw size={14} /> Refresh</button>}>{error && <div className="settings-error">{error}</div>}<table className="settings-table"><thead><tr><th>Connection</th><th>Status</th><th>Detail</th><th>Endpoint</th></tr></thead><tbody>{checks.map(c => <tr key={c.name}><td>{c.name}</td><td><StatusPill value={c.status} /></td><td className="settings-muted">{c.detail || 'No detail'}</td><td><EndpointBadge>{c.endpoint}</EndpointBadge></td></tr>)}</tbody></table><div className="settings-detail-body"><EnvironmentServiceTable services={services} /></div></SettingCard>
}

function SessionsSettings({ sessions, error, onRefresh, onNavigate }: { sessions: SessionRecord[]; error: string; onRefresh: () => void; onNavigate: (path: string) => void }) {
  return <SettingCard title="Sessions" description="Backed by GET /api/sessions." action={<button className="settings-btn" onClick={onRefresh}><RefreshCw size={14} /> Refresh</button>}>{error && <div className="settings-error">{error}</div>}{!sessions.length ? <div className="settings-empty">No sessions returned by the control plane.</div> : <table className="settings-table"><thead><tr><th>Session</th><th>Status</th><th>Repository</th><th>Created</th></tr></thead><tbody>{sessions.map(s => <tr key={s.id}><td><button className="settings-btn" onClick={() => onNavigate(`/session/${s.id}`)}>{truncStr(s.id, 18)}</button></td><td><StatusPill value={s.status} /></td><td>{s.repo_path || 'unknown'}</td><td>{relativeTime(s.created_at)}</td></tr>)}</tbody></table>}</SettingCard>
}

function UsageSettings({ health, error, onRefresh }: { health: Health; error: string; onRefresh: () => void }) {
  return <SettingCard title="Usage and limits" description="Backed by GET /api/health. Hard quota controls are hidden until a quota endpoint exists." action={<button className="settings-btn" onClick={onRefresh}><RefreshCw size={14} /> Refresh</button>}>{error && <div className="settings-error">{error}</div>}<InfoRows rows={[{ label: 'Disk used', value: `${health.disk?.used || '?'} / ${health.disk?.available || '?'} free (${health.disk?.percent || '?'})` }, { label: 'Memory used', value: `${health.memory?.used || '?'} / ${health.memory?.total || '?'}` }, { label: 'CPU load', value: `${health.cpu?.load_1m || '?'} / ${health.cpu?.load_5m || '?'} / ${health.cpu?.load_15m || '?'}` }, { label: 'Active ports', value: health.active_ports?.length ? health.active_ports.join(', ') : 'none reported' }]} /></SettingCard>
}

function AgentSettings({ models, services, error, onRefresh }: { models: { live: ModelInfo[]; configured: ModelInfo[] }; services: ServiceInfo[]; error: string; onRefresh: () => void }) {
  const agentServices = services.filter(s => ['agent-core', 'litellm', 'vendor-runtime', 'control-plane'].includes(s.name))
  return <><SettingCard title="Models" description="Backed by GET /api/models." action={<button className="settings-btn" onClick={onRefresh}><RefreshCw size={14} /> Refresh</button>}>{error && <div className="settings-error">{error}</div>}<InfoRows rows={[{ label: 'Live models', value: models.live?.length || 0 }, { label: 'Configured models', value: models.configured?.length || 0 }]} /><div className="settings-detail-body settings-list">{(models.live?.length ? models.live : models.configured || []).slice(0, 12).map((m, i) => <div key={m.id || m.model_name || i} className="settings-list-item"><span><span className="settings-list-title">{m.id || m.model_name || `model-${i + 1}`}</span><span className="settings-list-sub">{m.litellm_params?.model || m.object || 'model metadata'}</span></span></div>)}{!models.live?.length && !models.configured?.length && <div className="settings-empty">No models returned.</div>}</div></SettingCard><SettingCard title="Agent services" description="Backed by GET /api/services."><EnvironmentServiceTable services={agentServices} /></SettingCard></>
}

function KnowledgeSettings({ entries, proposed, error, onRefresh }: { entries: KnowledgeEntry[]; proposed: KnowledgeEntry[]; error: string; onRefresh: () => void }) {
  return <SettingCard title="Knowledge" description="Backed by GET /api/knowledge and GET /api/knowledge/proposed." action={<button className="settings-btn" onClick={onRefresh}><RefreshCw size={14} /> Refresh</button>}>{error && <div className="settings-error">{error}</div>}<InfoRows rows={[{ label: 'Approved entries', value: entries.length }, { label: 'Proposed triggers', value: proposed.length }]} /><div className="settings-detail-body settings-list">{[...entries, ...proposed].slice(0, 12).map((entry, i) => <div key={entry.id || entry.name || entry.title || i} className="settings-list-item"><span><span className="settings-list-title">{entry.title || entry.name || entry.id || `knowledge-${i + 1}`}</span><span className="settings-list-sub">{entry.description || entry.content || 'Knowledge entry'}</span></span></div>)}{!entries.length && !proposed.length && <div className="settings-empty">No knowledge entries returned.</div>}</div></SettingCard>
}

function RemoteDesktopSettings({ config, health, error, onRefresh, onOpen }: { config: RemoteDesktopConfig | null; health: RemoteDesktopHealth | null; error: string; onRefresh: () => void; onOpen: () => void }) {
  return <SettingCard title="Remote Desktop" description="Backed by GET /api/v2/remote-desktop/config and GET /api/v2/remote-desktop/health." action={<button className="settings-btn" onClick={onRefresh}><RefreshCw size={14} /> Refresh</button>}>{error && <div className="settings-error">{error}</div>}<InfoRows rows={[{ label: 'Enabled', value: <StatusPill value={config?.enabled} /> }, { label: 'Provider', value: config?.provider || 'unknown' }, { label: 'Gateway', value: <StatusPill value={health?.guacamole} /> }, { label: 'RDP target', value: `${health?.rdp_host || config?.rdp_host || 'unknown'}:${health?.rdp_port || 3389}` }, { label: 'RDP status', value: <StatusPill value={health?.rdp} /> }, { label: 'Security', value: config?.security?.replace('_', ' ') || 'unknown' }]} /><div className="settings-detail-body"><button className="settings-btn settings-btn-primary" onClick={onOpen}><Monitor size={14} /> Open Remote Desktop</button></div></SettingCard>
}

function SkillsSettings({ entries, proposed, error, onRefresh }: { entries: KnowledgeEntry[]; proposed: KnowledgeEntry[]; error: string; onRefresh: () => void }) {
  return <SettingCard title="Skills & Rules" description="No dedicated skills endpoint exists yet. This panel is intentionally backed by knowledge and proposed trigger endpoints." action={<button className="settings-btn" onClick={onRefresh}><RefreshCw size={14} /> Refresh</button>}>{error && <div className="settings-error">{error}</div>}<div className="settings-warning">A dedicated skills/rules registry should replace this panel later. Until then, it shows only what existing endpoints can support.</div><InfoRows rows={[{ label: 'Knowledge entries', value: entries.length }, { label: 'Proposed rules', value: proposed.length }]} /></SettingCard>
}

function EnvironmentSettings({ services, error, onRefresh }: { services: ServiceInfo[]; error: string; onRefresh: () => void }) {
  return <SettingCard title="Environment services" description="Backed by GET /api/services plus service start/stop/restart/update endpoints." action={<button className="settings-btn" onClick={onRefresh}><RefreshCw size={14} /> Refresh</button>}>{error && <div className="settings-error">{error}</div>}<EnvironmentServiceTable services={services} /></SettingCard>
}

function EnvironmentServiceTable({ services }: { services: ServiceInfo[] }) {
  if (!services.length) return <div className="settings-empty">No services returned.</div>
  return <table className="settings-table"><thead><tr><th>Service</th><th>Status</th><th>Port</th><th>Repo-backed</th></tr></thead><tbody>{services.map(s => <tr key={s.name}><td><strong>{s.name}</strong><div className="settings-muted">{s.description}</div></td><td><StatusPill value={s.status} /></td><td>{s.port}</td><td>{s.repo_backed ? 'yes' : 'no'}</td></tr>)}</tbody></table>
}

function RepositoriesSettings({ sessions, browse, error, onRefresh }: { sessions: SessionRecord[]; browse: { entries: BrowseEntry[]; path?: string; error?: string }; error: string; onRefresh: () => void }) {
  const sessionRepos = Array.from(new Set(sessions.map(s => s.repo_path).filter(Boolean)))
  const browsedRepos = browse.entries.filter(e => e.is_repo)
  return <SettingCard title="Repositories" description="Backed by GET /api/sessions and GET /api/browse?path=/opt/workstation/repos." action={<button className="settings-btn" onClick={onRefresh}><RefreshCw size={14} /> Refresh</button>}>{error && <div className="settings-error">{error}</div>}<InfoRows rows={[{ label: 'Session repositories', value: sessionRepos.length }, { label: 'Browse path', value: browse.path || '/opt/workstation/repos' }, { label: 'Repos in browse path', value: browsedRepos.length }]} /><div className="settings-detail-body settings-list">{[...sessionRepos.map(path => ({ name: path.split('/').pop() || path, path })), ...browsedRepos].slice(0, 16).map(repo => <div key={repo.path} className="settings-list-item"><span><span className="settings-list-title">{repo.name}</span><span className="settings-list-sub">{repo.path}</span></span><GitBranch size={14} /></div>)}{!sessionRepos.length && !browsedRepos.length && <div className="settings-empty">No repositories found.</div>}</div></SettingCard>
}

function ApiSettings({ health }: { health: Health }) {
  const endpoints = [['GET', '/api/health', 'Control-plane service, disk, memory, CPU, Docker, and ports.'], ['GET', '/api/services', 'Known workstation services.'], ['POST', '/api/services/{name}/start', 'Start a known service.'], ['POST', '/api/services/{name}/stop', 'Stop a known service.'], ['POST', '/api/services/{name}/restart', 'Restart a known service.'], ['POST', '/api/v2/services/{name}/update-latest', 'Update a repo-backed service from GitHub.'], ['GET', '/api/sessions', 'Session list.'], ['GET', '/api/models', 'LiteLLM model inventory.'], ['GET', '/api/knowledge', 'Approved knowledge entries.'], ['GET', '/api/knowledge/proposed', 'Proposed knowledge triggers.'], ['GET', '/api/browse?path=...', 'Filesystem browsing for safe repo roots.'], ['GET', '/api/session-graph/settings/observability', 'Read observability settings.'], ['PUT', '/api/session-graph/settings/observability', 'Save observability settings.'], ['GET', '/api/v2/remote-desktop/config', 'Remote desktop configuration.'], ['GET', '/api/v2/remote-desktop/health', 'Remote desktop reachability checks.'], ['POST', '/api/v2/remote-desktop/token', 'Guacamole token when auto-login is enabled.']]
  return <SettingCard title="Settings endpoint inventory" description="Complete endpoint surface used by this settings screen."><InfoRows rows={[{ label: 'Agent core status', value: <StatusPill value={health.agent_core?.status} /> }, { label: 'LiteLLM status', value: <StatusPill value={health.litellm?.status} /> }]} /><div className="settings-detail-body"><table className="settings-table"><thead><tr><th>Method</th><th>Endpoint</th><th>Purpose</th></tr></thead><tbody>{endpoints.map(([method, path, purpose]) => <tr key={`${method}:${path}`}><td>{method}</td><td><EndpointBadge>{path}</EndpointBadge></td><td>{purpose}</td></tr>)}</tbody></table></div></SettingCard>
}

function RemoteDesktopPage() {
  const [config, setConfig] = useState<RemoteDesktopConfig | null>(null)
  const [remoteHealth, setRemoteHealth] = useState<RemoteDesktopHealth | null>(null)
  const [error, setError] = useState('')
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [frameSrc, setFrameSrc] = useState('')
  const [autoLoginStatus, setAutoLoginStatus] = useState('')
  const frameShellRef = useRef<HTMLDivElement>(null)
  const refresh = useCallback(() => { fetchJson<RemoteDesktopConfig>('/v2/remote-desktop/config').then(setConfig).catch(err => setError((err as Error).message)); fetchJson<RemoteDesktopHealth>('/v2/remote-desktop/health').then(setRemoteHealth).catch(() => {}) }, [])
  useEffect(() => { refresh(); const id = setInterval(refresh, 10000); return () => clearInterval(id) }, [refresh])
  useEffect(() => { const fn = () => { setIsFullscreen(document.fullscreenElement === frameShellRef.current) }; document.addEventListener('fullscreenchange', fn); return () => document.removeEventListener('fullscreenchange', fn) }, [])
  const toggleFullscreen = useCallback(() => { const el = frameShellRef.current; if (!el) return; if (document.fullscreenElement) { document.exitFullscreen().catch(e => setError((e as Error).message)); return } el.requestFullscreen().catch(e => setError((e as Error).message)) }, [])
  const startGuacamoleSession = useCallback(() => { if (!config?.enabled) return; if (!config.auto_login) { setFrameSrc(config.url); setAutoLoginStatus(''); return }; setAutoLoginStatus('Signing in...'); fetch(endpoint('/v2/remote-desktop/token'), { method: 'POST' }).then(async r => { if (!r.ok) throw new Error(await r.text() || 'Unable to sign in'); return r.json() as Promise<GuacamoleSession> }).then(session => { localStorage.setItem('GUAC_AUTH', JSON.stringify({ authToken: session.authToken, username: session.username, dataSource: session.dataSource, availableDataSources: session.availableDataSources })); setFrameSrc(session.connection_url || config.url); setAutoLoginStatus('Signed in') }).catch(err => { setAutoLoginStatus(`Auto-login failed: ${(err as Error).message}`); setFrameSrc(config.url) }) }, [config])
  useEffect(() => { if (config?.enabled) startGuacamoleSession() }, [config, startGuacamoleSession])
  if (error) return <div className="remote-desktop-page"><div className="remote-card"><h2>Remote Desktop</h2><p className="remote-error">Unable to load config: {error}</p></div></div>
  if (!config) return <div className="remote-desktop-page"><div className="remote-card">Loading remote desktop status...</div></div>
  const overallStatus = config.enabled ? (remoteHealth?.ok ? 'ready' : 'degraded') : 'disabled'
  return <div className="remote-desktop-page"><div className="remote-header"><div><h2>Remote Desktop</h2><p>Browser access through the remote desktop gateway.</p></div><button className="btn-refresh" onClick={refresh}><RefreshCw size={14} /> Refresh</button></div><div className="remote-status-grid"><div className="remote-status-card"><span className="remote-label">Connection</span><strong className={`remote-status remote-status-${overallStatus}`}>{overallStatus}</strong></div><div className="remote-status-card"><span className="remote-label">Gateway</span><strong>{remoteHealth?.guacamole || 'unknown'}</strong></div><div className="remote-status-card"><span className="remote-label">RDP target</span><strong>{remoteHealth?.rdp || 'unknown'}</strong><small>{remoteHealth?.rdp_host || config.rdp_host}:{remoteHealth?.rdp_port || 3389}</small></div><div className="remote-status-card"><span className="remote-label">Security</span><strong>{config.security.replace('_', ' ')}</strong></div></div>{!config.enabled ? <div className="remote-card remote-disabled"><h3>Remote desktop is disabled</h3><p>Enable the remote desktop service.</p></div> : <div ref={frameShellRef} className="remote-frame-shell"><div className="remote-frame-toolbar"><div className="remote-frame-title"><span>Remote Desktop</span>{autoLoginStatus && <small>{autoLoginStatus}</small>}</div><div className="remote-frame-actions"><button className="btn-refresh" onClick={startGuacamoleSession}><RefreshCw size={14} /> Reconnect</button><button className="btn-refresh" onClick={toggleFullscreen}>{isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}{isFullscreen ? 'Exit' : 'Full Screen'}</button></div></div>{frameSrc ? <iframe title="Remote Desktop" src={frameSrc} className="remote-frame" allow="fullscreen; clipboard-read; clipboard-write" allowFullScreen /> : <div className="remote-frame-loading">Opening remote desktop...</div>}</div>}</div>
}

function PortManager() {
  const [services, setServices] = useState<ServiceInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [updateLoading, setUpdateLoading] = useState<Record<string, boolean>>({})
  const [updateError, setUpdateError] = useState<Record<string, string>>({})
  const [updateSuccess, setUpdateSuccess] = useState<Record<string, string>>({})
  const fetchServices = useCallback(() => { fetchJson<{ services: ServiceInfo[] }>('/services').then(data => setServices(data.services || [])).catch(() => {}).finally(() => setLoading(false)) }, [])
  useEffect(() => { fetchServices(); const id = setInterval(fetchServices, 5000); return () => clearInterval(id) }, [fetchServices])
  const waitForStatus = async (name: string, status: ServiceInfo['status'], attempts = 10) => { for (let i = 0; i < attempts; i++) { const data = await fetchJson<{ services: ServiceInfo[] }>('/services'); setServices(data.services || []); if ((data.services || []).find((s: ServiceInfo) => s.name === name)?.status === status) return; await new Promise(r => setTimeout(r, 1000)) } }
  const startService = async (name: string) => { setActionLoading(`${name}:start`); try { await fetch(endpoint(`/services/${name}/start`), { method: 'POST' }); await waitForStatus(name, 'running'); if (name === 'dashboard') window.location.reload() } catch {} setActionLoading(null) }
  const stopService = async (name: string) => { setActionLoading(`${name}:stop`); try { await fetch(endpoint(`/services/${name}/stop`), { method: 'POST' }); await waitForStatus(name, 'stopped') } catch {} setActionLoading(null) }
  const updateLatest = async (name: string) => { setUpdateLoading(p => ({ ...p, [name]: true })); setUpdateError(p => { const n = { ...p }; delete n[name]; return n }); setUpdateSuccess(p => { const n = { ...p }; delete n[name]; return n }); try { const res = await fetch(endpoint(`/v2/services/${name}/update-latest`), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ restart: true }) }); const data = await res.json(); if (data.ok && data.deferred) { setUpdateSuccess(p => ({ ...p, [name]: 'Updating...' })); for (let i = 0; i < 30; i++) { await new Promise(r => setTimeout(r, 2000)); try { const h = await fetch(endpoint('/health'), { signal: AbortSignal.timeout(3000) }); if (h.ok) { fetchServices(); break } } catch {} } setUpdateSuccess(p => ({ ...p, [name]: 'Updated.' })); setUpdateLoading(p => ({ ...p, [name]: false })); return } if (data.ok) { setUpdateSuccess(p => ({ ...p, [name]: data.message || 'Updated' })) } else { setUpdateError(p => ({ ...p, [name]: data.error?.message || 'Failed' })) } fetchServices() } catch { setUpdateError(p => ({ ...p, [name]: 'Network error' })) } setUpdateLoading(p => ({ ...p, [name]: false })) }
  const restartService = async (name: string) => { setActionLoading(`${name}:restart`); try { await fetch(endpoint(`/services/${name}/restart`), { method: 'POST' }); await waitForStatus(name, 'running', name === 'control-plane' ? 15 : 10); if (name === 'dashboard' || name === 'control-plane') window.location.reload() } catch {} setActionLoading(null) }
  if (loading) return <div className="port-manager"><div className="pm-loading">Discovering services...</div></div>
  return <div className="port-manager"><div className="pm-header"><Server size={16} /><span>Services</span><button className="pm-refresh" onClick={fetchServices} title="Refresh"><RefreshCw size={14} /></button></div><div className="pm-list">{services.map(svc => <div key={svc.name} className={`pm-item pm-${svc.status}`}><div className="pm-item-info"><Circle size={8} fill={svc.status === 'running' ? '#4ade80' : '#94a3b8'} stroke={svc.status === 'running' ? '#4ade80' : '#94a3b8'} /><span className="pm-name">{svc.name}</span><span className="pm-port">:{svc.port}</span>{svc.docker && <span className="pm-docker">docker</span>}</div><div className="pm-item-desc">{svc.description}</div>{updateError[svc.name] && <div className="pm-update-msg pm-update-error">{updateError[svc.name]}</div>}{updateSuccess[svc.name] && <div className="pm-update-msg pm-update-success">{updateSuccess[svc.name]}</div>}<div className="pm-item-actions">{actionLoading?.startsWith(`${svc.name}:`) ? <span className="pm-busy">...</span> : svc.status === 'running' ? <>{svc.can_restart !== false && <button className="pm-btn pm-btn-restart" onClick={() => restartService(svc.name)} title="Restart"><RefreshCw size={12} /></button>}{svc.repo_backed && <button className={`pm-btn pm-btn-update${updateLoading[svc.name] ? ' pm-btn-updating' : ''}`} onClick={() => updateLatest(svc.name)} disabled={!svc.update_supported || updateLoading[svc.name] || svc.update_in_progress} title="Update latest"><Download size={12} className={updateLoading[svc.name] ? 'pm-spin' : ''} /></button>}{svc.can_stop !== false && <button className="pm-btn pm-btn-stop" onClick={() => stopService(svc.name)} title="Stop"><Power size={12} /></button>}</> : <>{svc.can_start !== false && <button className="pm-btn pm-btn-start" onClick={() => startService(svc.name)} title="Start"><Power size={12} /></button>}{svc.repo_backed && <button className={`pm-btn pm-btn-update${updateLoading[svc.name] ? ' pm-btn-updating' : ''}`} onClick={() => updateLatest(svc.name)} disabled={!svc.update_supported || updateLoading[svc.name] || svc.update_in_progress} title="Update latest"><Download size={12} className={updateLoading[svc.name] ? 'pm-spin' : ''} /></button>}</>}</div></div>)}</div></div>
}

function FolderBrowser({ onSelect }: { onSelect: (path: string) => void }) {
  const [currentPath, setCurrentPath] = useState('/opt/workstation/repos')
  const [entries, setEntries] = useState<BrowseEntry[]>([])
  const [parentPath, setParentPath] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const browse = useCallback((path: string) => { setLoading(true); fetchJson<{ path?: string; entries?: BrowseEntry[]; parent?: string }>(`/browse?path=${encodeURIComponent(path)}`).then(data => { setCurrentPath(data.path || path); setEntries(data.entries || []); setParentPath(data.parent || null) }).catch(() => {}).finally(() => setLoading(false)) }, [])
  useEffect(() => { browse(currentPath) }, [])
  return <div className="folder-browser"><div className="browser-header"><span className="browser-path">{currentPath}</span></div><div className="browser-entries">{parentPath && currentPath !== '/' && <div className="browser-entry" onClick={() => browse(parentPath)}><ArrowUp size={16} className="entry-icon-svg" /><span className="entry-name">..</span></div>}{loading && <div className="browser-loading">Loading...</div>}{entries.map(entry => <div key={entry.path} className={`browser-entry ${entry.is_repo ? 'is-repo' : ''}`} onClick={() => entry.is_repo ? onSelect(entry.path) : browse(entry.path)}>{entry.is_repo ? <GitBranch size={16} className="entry-icon-svg repo-icon" /> : <Folder size={16} className="entry-icon-svg" />}<span className="entry-name">{entry.name}</span>{entry.is_repo && <span className="entry-badge">repo</span>}</div>)}{!loading && entries.length === 0 && <div className="browser-empty">Empty directory</div>}</div></div>
}

function ResizeDivider({ onResize }: { onResize: (delta: number) => void }) {
  const dragging = useRef(false)
  const lastX = useRef(0)
  const onMouseDown = useCallback((e: React.MouseEvent) => { e.preventDefault(); dragging.current = true; lastX.current = e.clientX; document.body.style.cursor = 'col-resize'; document.body.style.userSelect = 'none'; const onMove = (ev: MouseEvent) => { if (!dragging.current) return; onResize(ev.clientX - lastX.current); lastX.current = ev.clientX }; const onUp = () => { dragging.current = false; document.body.style.cursor = ''; document.body.style.userSelect = ''; document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp) }; document.addEventListener('mousemove', onMove); document.addEventListener('mouseup', onUp) }, [onResize])
  return <div className="resize-divider" onMouseDown={onMouseDown} />
}

export default function App() {
  const [sessions, setSessions] = useState<SessionRecord[]>([])
  const [newSessionRepo, setNewSessionRepo] = useState('agent-core')
  const [showBrowser, setShowBrowser] = useState(true)
  const [routePath, setRoutePath] = useState(window.location.pathname)
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
  const fetchSessions = useCallback(() => { fetchJson<{ sessions: SessionRecord[] }>('/sessions').then(d => setSessions(d.sessions || [])).catch(() => {}) }, [])
  useEffect(() => { fetchSessions(); const id = setInterval(fetchSessions, 10000); return () => clearInterval(id) }, [fetchSessions])
  useEffect(() => { if (searchOpen) searchInputRef.current?.focus() }, [searchOpen])
  const createSession = async () => { const name = `session-${Date.now().toString(36)}`; const res = await fetch(endpoint('/sessions'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, repo: newSessionRepo }) }); const data = await res.json(); if (data.id) { fetchSessions(); navigate(`/session/${data.id}`) } }
  const destroySession = async (id: string) => { await fetch(endpoint(`/sessions/${id}`), { method: 'DELETE' }); fetchSessions(); if (routePath === `/session/${id}`) navigate('/') }
  const sortedSessions = [...sessions].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
  const filteredSessions = sortedSessions.filter(s => { if (!searchQuery) return true; const l = s.repo_path?.split('/').pop() || s.id; return l.toLowerCase().includes(searchQuery.toLowerCase()) || s.id.toLowerCase().includes(searchQuery.toLowerCase()) })
  const handleSidebarResize = useCallback((delta: number) => { setSidebarWidth(prev => Math.max(180, Math.min(400, prev + delta))) }, [])
  if (routePath === '/settings') return <SettingsPage workspaceName={workspaceName} onBack={() => navigate('/')} onNavigate={navigate} />
  const navItems = [{ key: 'sessions', label: 'Sessions', icon: <Layers size={16} />, path: '/' }, { key: 'graph', label: 'Session Graph', icon: <GitBranch size={16} />, badge: 'New', path: '/session-graph' }, { key: 'knowledge', label: 'Knowledge', icon: <BookOpen size={16} />, path: '/settings' }, { key: 'remote-desktop', label: 'Remote Desktop', icon: <Monitor size={16} />, path: '/remote-desktop' }]
  return <div className="app-shell"><aside className="app-sidebar" style={{ width: sidebarCollapsed ? 52 : sidebarWidth }} aria-label="Workspace sidebar">{sidebarCollapsed ? <><button className="sidebar-expand-btn" onClick={() => setSidebarCollapsed(false)} aria-label="Expand sidebar"><ChevronRight size={16} /></button><div className="sidebar-collapsed-nav">{navItems.map(n => <button key={n.key} className={`sidebar-icon-btn ${navActive === n.key ? 'active' : ''}`} onClick={() => { setNavActive(n.key); navigate(n.path); setSidebarCollapsed(false) }} title={n.label} aria-label={n.label}>{n.icon}</button>)}</div><div className="sidebar-collapsed-footer"><button className="sidebar-icon-btn" onClick={() => navigate('/settings')} title="Settings" aria-label="Settings"><Settings size={16} /></button></div></> : <><div className="sidebar-ws-header"><button className="ws-trigger" onClick={() => setWsDropdownOpen(!wsDropdownOpen)} aria-haspopup="true" aria-expanded={wsDropdownOpen} aria-label="Workspace menu"><div className="ws-avatar-sm">{workspaceName.charAt(0).toUpperCase()}</div><span className="ws-name-text">{workspaceName}</span><ChevronDown size={14} className="ws-chevron" /></button><button className="sidebar-collapse-btn" onClick={() => setSidebarCollapsed(true)} aria-label="Collapse sidebar"><ChevronLeft size={16} /></button><WorkspaceDropdown workspaceName={workspaceName} open={wsDropdownOpen} onClose={() => setWsDropdownOpen(false)} onSettings={() => { setWsDropdownOpen(false); navigate('/settings') }} /></div><nav className="sidebar-primary-nav" aria-label="Primary navigation">{navItems.map(n => <button key={n.key} className={`sidebar-nav-item ${navActive === n.key ? 'active' : ''}`} onClick={() => { setNavActive(n.key); navigate(n.path) }} aria-label={n.label}>{n.icon} <span>{n.label}</span>{n.badge && <span className="sidebar-badge">{n.badge}</span>}</button>)}</nav><div className="sidebar-recent">{searchOpen ? <div className="sidebar-search-bar"><Search size={12} /><input ref={searchInputRef} className="sidebar-search-input" placeholder="Search sessions..." value={searchQuery} onChange={e => setSearchQuery(e.target.value)} onKeyDown={e => { if (e.key === 'Escape') { setSearchOpen(false); setSearchQuery('') } }} aria-label="Search sessions" /><button className="sidebar-search-close" onClick={() => { setSearchOpen(false); setSearchQuery('') }} aria-label="Close search"><X size={12} /></button></div> : <div className="sidebar-recent-header"><span className="sidebar-recent-label">Recent</span><div className="sidebar-recent-actions"><button className="sidebar-icon-btn" onClick={() => setSearchOpen(true)} title="Search sessions" aria-label="Search sessions"><Search size={14} /></button><button className="sidebar-icon-btn" onClick={createSession} title="New session" aria-label="New session"><Plus size={14} /></button><button className="sidebar-icon-btn" onClick={() => setRecentMenuOpen(!recentMenuOpen)} title="More options" aria-label="More options" aria-haspopup="true" aria-expanded={recentMenuOpen}><MoreHorizontal size={14} /></button></div><RecentMenu open={recentMenuOpen} onClose={() => setRecentMenuOpen(false)} sortBy={sortBy} onSortChange={v => { setSortBy(v); setRecentMenuOpen(false) }} filters={filters} onFilterToggle={k => setFilters(p => ({ ...p, [k]: !p[k] }))} /></div>}<div className="sidebar-session-list">{filteredSessions.map(s => { const label = s.repo_path?.split('/').pop() || s.id; const isActive = routePath === `/session/${s.id}`; const isLive = s.status === 'running'; return <div key={s.id} className={`sidebar-session-row ${isActive ? 'active' : ''}`} onClick={() => navigate(`/session/${s.id}`)} role="button" tabIndex={0} aria-label={`Session: ${label}`}><div className="sidebar-session-top"><span className="sidebar-session-name">{truncStr(label, 24)}</span>{isLive && <span className="sidebar-live-dot" />}<button className="sidebar-session-destroy" onClick={e => { e.stopPropagation(); destroySession(s.id) }} title="Delete session" aria-label="Delete session"><X size={12} /></button></div><div className="sidebar-session-meta"><span>{relativeTime(s.created_at)}</span>{s.repo_path && <span className="sidebar-session-repo"><GitBranch size={10} /> {s.repo_path.split('/').pop()}</span>}</div></div> })}{filteredSessions.length === 0 && <div className="sidebar-empty">No sessions found.</div>}</div></div><div className="sidebar-footer"><button className="sidebar-nav-item" onClick={() => navigate('/settings')} aria-label="Settings"><Settings size={16} /> <span>Settings</span></button><button className="sidebar-icon-btn" title="Help" aria-label="Help"><HelpCircle size={16} /></button></div></>}</aside>{!sidebarCollapsed && <ResizeDivider onResize={handleSidebarResize} />}<main className="app-main">{routePath.startsWith('/session/') ? <AgentSessionPage sessionId={routePath.replace('/session/', '')} onBack={() => navigate('/')} sessions={sessions} onNavigateSession={id => navigate(`/session/${id}`)} /> : routePath === '/remote-desktop' ? <RemoteDesktopPage /> : routePath === '/session-graph' ? <SessionGraphExplorer /> : <div className="welcome"><h2>Agent Workspace</h2><p>Create or select a session to start working.</p><div className="welcome-actions"><div className="repo-input-row"><input className="repo-input" value={newSessionRepo} onChange={e => setNewSessionRepo(e.target.value)} placeholder="Repo name or path..." /><button className="btn-browse" onClick={() => setShowBrowser(!showBrowser)}><Folder size={14} />{showBrowser ? 'Close' : 'Browse...'}</button></div><button className="btn-start" onClick={createSession}>Start Session</button></div>{showBrowser && <FolderBrowser onSelect={path => { setNewSessionRepo(path); setShowBrowser(false) }} />}<PortManager /></div>}</main></div>
}
