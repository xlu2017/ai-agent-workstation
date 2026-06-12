/**
 * AgentSessionPage renders a backend-backed live session transcript.
 *
 * Every visible control either calls an existing control-plane endpoint, performs
 * a browser-local action such as copy/open-link, or is not rendered. Future-only
 * controls such as attachments, voice input, arbitrary tab creation, and prompt
 * approval buttons are intentionally omitted until corresponding endpoints exist.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  AlertTriangle, BookOpen, Camera, Check, CheckCircle, ChevronDown, ChevronLeft,
  ChevronRight, Circle, Clock, Copy, ExternalLink, File, FileText, GitBranch,
  GitCommit, GitPullRequest, Keyboard, Loader, Monitor, MousePointer, RefreshCw,
  Search, Send, Shield, SkipForward, Square, Terminal, Upload, X, XCircle,
} from 'lucide-react'

interface SessionEvent {
  event_type: string
  session_id: string
  data: Record<string, any>
  event_id: string
  timestamp: string
  sequence?: number
  _seq?: number
}

interface RepoRef { provider: string; owner: string; repo: string }
type PlanStepStatus = 'pending' | 'active' | 'completed' | 'failed' | 'blocked' | 'skipped'
interface PlanStep { id: string; index: number; title: string; status: PlanStepStatus }
interface TranscriptEntry { kind: string; label: string; status: string; timestamp: string; duration_ms?: number; metadata?: Record<string, any> }
interface TranscriptData {
  session_id: string
  headline: string
  working_duration_ms: number
  additions: number
  deletions: number
  tasks_created: number
  items: TranscriptEntry[]
  validation: { overall: string; commands: Array<Record<string, any>> }
}
interface TimelinePoint {
  id: string
  timestamp: string
  offsetMs: number
  kind: 'prompt' | 'action' | 'desktop_state' | 'desktop_snapshot' | 'worklog' | 'change' | 'pr' | 'error' | 'status'
  title: string
  summary?: string
  prompt?: string
  url?: string
  desktopActive?: boolean
}
interface TimelineSegment { id: string; startOffsetMs: number; endOffsetMs: number; desktopActive: boolean; eventCount: number }
interface TimelineData { points: TimelinePoint[]; segments: TimelineSegment[]; duration_ms: number }
interface SessionRecord { id: string; status: string; repo_path: string; created_at: string }
interface RemoteDesktopConfig { enabled: boolean; provider: string; url: string; rdp_host: string; security: string; auto_login: boolean }
interface GuacamoleSession { authToken: string; username: string; dataSource: string; availableDataSources: string[]; connection_url: string }

const API = '/api'
const CONTROL_API = window.location.port === '5173'
  ? `${window.location.protocol}//${window.location.hostname}:9877/api`
  : API

function apiPath(path: string) { return `${CONTROL_API}${path.startsWith('/') ? path : `/${path}`}` }

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiPath(path), init)
  if (!response.ok) throw new Error(await response.text() || `${response.status} ${response.statusText}`)
  return response.json() as Promise<T>
}

function formatDuration(ms: number): string {
  const secs = Math.max(0, Math.floor(ms / 1000))
  if (secs < 60) return `${secs}s`
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins}m ${secs % 60}s`
  return `${Math.floor(mins / 60)}h ${mins % 60}m`
}

function timeLabel(ts?: string): string {
  if (!ts) return ''
  try { return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) } catch { return '' }
}

function truncate(value: string, n: number): string { return value.length > n ? `${value.slice(0, n)}…` : value }
function basename(path = ''): string { return path.split('/').filter(Boolean).pop() || path || 'unknown' }
function eventMessage(event: SessionEvent): string { return event.data?.message || event.data?.summary || '' }

function copyToClipboard(value: string) {
  if (!value) return
  navigator.clipboard?.writeText(value).catch(() => undefined)
}

function emptyTranscript(sessionId: string): TranscriptData {
  return { session_id: sessionId, headline: '', working_duration_ms: 0, additions: 0, deletions: 0, tasks_created: 0, items: [], validation: { overall: 'not_run', commands: [] } }
}

function statusClass(status: string): string {
  if (['completed', 'passed', 'open', 'merged'].includes(status)) return 'completed'
  if (['failed', 'blocked', 'cancelled'].includes(status)) return 'failed'
  return status || 'pending'
}

function SessionTopBar({ title, model, onBack }: { title: string; model: string; onBack?: () => void }) {
  return <div className="as-topbar">{onBack && <button className="as-icon-btn" onClick={onBack} title="Back"><ChevronLeft size={16} /></button>}<span className="as-topbar-title">{title || 'Agent Session'}</span>{model && <span className="as-model-badge">{model}</span>}</div>
}

function MessageActionBar({ content, timestamp, anchorId }: { content: string; timestamp?: string; anchorId?: string }) {
  const copyLink = () => {
    const url = `${window.location.origin}${window.location.pathname}${anchorId ? `#${anchorId}` : ''}`
    copyToClipboard(url)
  }
  return <div className="as-msg-actions"><button className="as-icon-btn" title="Copy message" onClick={() => copyToClipboard(content)}><Copy size={14} /></button><button className="as-icon-btn" title="Copy link" onClick={copyLink}><ExternalLink size={14} /></button>{timestamp && <span className="as-msg-time">{timeLabel(timestamp)}</span>}</div>
}

function RepoAttachmentPill({ owner, repo }: { owner: string; repo: string }) {
  return <div className="as-repo-pill"><div className="as-repo-pill-icon"><GitBranch size={14} /></div><span>{owner}/{repo}</span></div>
}

function UserPromptMessage({ content, repos, timestamp, eventId }: { content: string; repos: RepoRef[]; timestamp?: string; eventId?: string }) {
  const [expanded, setExpanded] = useState(false)
  const needsCollapse = content.length > 400
  return <div className="as-user-prompt-row" id={eventId}><div className={`as-user-prompt ${!expanded && needsCollapse ? 'as-collapsed' : ''}`}><div className="as-prompt-md"><ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown></div>{needsCollapse && !expanded && <button className="as-prompt-fade" onClick={() => setExpanded(true)}><ChevronDown size={16} /></button>}{needsCollapse && expanded && <button className="as-prompt-collapse-btn" onClick={() => setExpanded(false)}>Collapse</button>}</div>{repos.length > 0 && <div className="as-repo-pills">{repos.map(r => <RepoAttachmentPill key={`${r.owner}/${r.repo}`} owner={r.owner} repo={r.repo} />)}</div>}<MessageActionBar content={content} timestamp={timestamp} anchorId={eventId} /><div className="as-user-avatar">U</div></div>
}

function AgentMessage({ content, timestamp, eventId }: { content: string; timestamp?: string; eventId?: string }) {
  return <div className="as-agent-msg" id={eventId}><div className="as-agent-msg-text"><ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown></div><MessageActionBar content={content} timestamp={timestamp} anchorId={eventId} /></div>
}

function ExecutionPlanCard({ steps }: { steps: PlanStep[] }) {
  const currentIndex = Math.max(0, steps.findIndex(step => step.status === 'active'))
  const currentTitle = steps[currentIndex]?.title || steps[0]?.title || ''
  return <div className="as-plan-card"><div className="as-plan-header"><span className="as-plan-counter">{steps.length ? currentIndex + 1 : 0}/{steps.length}</span><span className="as-plan-current">{currentTitle}</span></div><div className="as-plan-title-row">Execution plan</div><div className="as-plan-steps">{steps.map(step => <div key={step.id} className={`as-plan-step as-step-${step.status}`}><span className="as-step-icon">{step.status === 'completed' && <Check size={14} />}{step.status === 'active' && <Loader size={14} className="as-spin" />}{step.status === 'failed' && <X size={14} />}{step.status === 'blocked' && <Shield size={14} />}{step.status === 'pending' && <Circle size={12} />}</span><span className="as-step-label">{step.title}</span></div>)}</div></div>
}

function ToolRow({ item }: { item: TranscriptEntry }) {
  const [open, setOpen] = useState(false)
  const meta = item.metadata || {}
  const icon = item.kind === 'command' || item.kind === 'test' ? <Terminal size={14} /> : item.kind === 'search' ? <Search size={14} /> : item.kind === 'edit' || item.kind === 'diff' ? <FileText size={14} /> : item.kind === 'read' ? <File size={14} /> : item.kind === 'thought' ? <Clock size={14} /> : <Circle size={12} />
  const command = meta.command as string | undefined
  const path = meta.path as string | undefined
  const hasDetails = Boolean(command || path || Object.keys(meta).length > 0)
  return <div className={`as-file-row as-row-${statusClass(item.status)}`}><button className="as-icon-btn" disabled={!hasDetails} onClick={() => setOpen(!open)} title={hasDetails ? 'Toggle details' : 'No details'}>{open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</button>{icon}<span className="as-file-kind">{item.kind.replace(/_/g, ' ')}</span><span className="as-file-summary">{item.label}</span>{item.duration_ms ? <span className="as-cmd-dur">{formatDuration(item.duration_ms)}</span> : null}{open && <div className="as-code-card" style={{ width: '100%' }}>{command && <code className="as-cmd-text">{command}</code>}{path && <div className="as-code-path">{path}</div>}<pre className="as-code-block">{JSON.stringify(meta, null, 2)}</pre></div>}</div>
}

function AgentErrorBlock({ title, body }: { title: string; body?: string }) {
  return <div className="as-error-block"><div className="as-error-header"><AlertTriangle size={16} /><span>Agent error</span></div><div className="as-error-title">{title}</div>{body && <div className="as-error-body">{body}</div>}</div>
}

function DecisionPromptCard({ question, options, status }: { question: string; options?: string[]; status: string }) {
  return <div className={`as-decision-card as-decision-${status}`}><div className="as-decision-q">Q: {question}</div>{options?.length ? <div className="as-decision-options">{options.map((option, index) => <button key={index} className="as-decision-opt-btn" disabled title="Decision-response endpoint is not implemented yet">{option}</button>)}</div> : null}<div className="as-file-summary">Waiting is displayed from backend events. Option submission is hidden until a response endpoint exists.</div></div>
}

function CommitCard({ hash, message, branch }: { hash: string; message: string; branch?: string }) {
  return <div className="as-commit-card"><GitCommit size={16} className="as-commit-icon" /><div className="as-commit-body"><code className="as-commit-hash">{hash ? hash.slice(0, 8) : 'unknown'}</code><span className="as-commit-msg">{message}</span>{branch && <span className="as-commit-branch">{branch}</span>}</div></div>
}

function PullRequestCard({ number, title, url, status }: { number: number; title: string; url?: string; status?: string }) {
  return <div className="as-pr-card"><GitPullRequest size={16} className="as-pr-icon" /><div className="as-pr-body"><span className="as-pr-number">#{number || '?'}</span><span className="as-pr-title">{title || 'Pull request'}</span>{status && <span className={`as-pr-status as-pr-${status}`}>{status}</span>}</div>{url && <a href={url} target="_blank" rel="noopener" className="as-pr-link" title="Open pull request"><ExternalLink size={14} /></a>}</div>
}

function BrowserActivityRow({ action, value, coordinates, duration }: { action: string; value?: string; coordinates?: { x: number; y: number }; duration?: number }) {
  const labels: Record<string, string> = { pressed_key: 'Pressed key', typed_text: 'Typed text', clicked: 'Clicked', double_clicked: 'Double-clicked', waited: 'Waited', screenshot: 'Took screenshot' }
  const Icon = action === 'pressed_key' ? Keyboard : action === 'clicked' || action === 'double_clicked' ? MousePointer : action === 'screenshot' ? Camera : Clock
  return <div className="as-browser-row"><Icon size={12} className="as-browser-icon" /><span className="as-browser-label">{labels[action] || action}</span>{value && action === 'pressed_key' && <code className="as-browser-val">{value}</code>}{value && action === 'typed_text' && <span className="as-browser-val">[redacted]</span>}{coordinates && <span className="as-browser-coords">({coordinates.x}, {coordinates.y})</span>}{duration !== undefined && <span className="as-browser-dur">{formatDuration(duration)}</span>}</div>
}

function LiveAgentStatus({ status, animated }: { status: string; animated?: boolean }) {
  if (!status) return null
  return <div className="as-live-status">{animated && <Loader size={14} className="as-spin" />}<span>{status}</span></div>
}

function parsePlanSteps(data: Record<string, any>): PlanStep[] {
  const raw = data.plan?.steps || data.plan || data.steps || []
  if (!Array.isArray(raw)) return []
  return raw.map((step: any, index: number) => ({ id: step.id || `step-${index}`, index, title: step.title || step.action_name || step.description || `Step ${index + 1}`, status: index === 0 ? 'active' : 'pending' }))
}

function eventToNode(event: SessionEvent): ReactNode | null {
  const d = event.data || {}
  const msg = eventMessage(event)
  const key = event.event_id
  switch (event.event_type) {
    case 'user_prompt_received': {
      const repos: RepoRef[] = []
      const matches = String(msg).match(/\b([\w.-]+)\/([\w.-]+)\b/g) || []
      for (const match of matches) {
        const [owner, repo] = match.split('/')
        if (owner && repo && !repos.some(r => r.owner === owner && r.repo === repo)) repos.push({ provider: 'github', owner, repo })
      }
      return <UserPromptMessage content={msg} repos={repos} timestamp={event.timestamp} eventId={key} />
    }
    case 'routing_decision_made':
    case 'task_started':
    case 'plan_requested':
    case 'plan_completed':
    case 'task_completed':
      return <AgentMessage content={msg || event.event_type.replace(/_/g, ' ')} timestamp={event.timestamp} eventId={key} />
    case 'plan_generated': {
      const steps = parsePlanSteps(d)
      return steps.length ? <ExecutionPlanCard steps={steps} /> : <AgentMessage content={msg || 'Plan generated'} timestamp={event.timestamp} eventId={key} />
    }
    case 'action_started':
      return <AgentMessage content={msg || `Started ${d.tool || d.action_name || 'action'}`} timestamp={event.timestamp} eventId={key} />
    case 'action_progress':
      if (d.tool === 'browser_action') return <BrowserActivityRow action={d.action || 'browser_action'} value={d.value} coordinates={d.coordinates} duration={d.duration_ms} />
      return <ToolRow item={{ kind: d.tool || 'action', label: msg || d.args_summary || d.tool || 'Action progress', status: 'completed', timestamp: event.timestamp, duration_ms: d.duration_ms, metadata: d }} />
    case 'file_read':
    case 'code_searched':
    case 'file_edited':
    case 'command_run':
    case 'test_run':
    case 'thought_elapsed':
    case 'validation_completed':
    case 'diff_summarized':
      return <ToolRow item={{ kind: event.event_type.replace('file_', '').replace('code_', '').replace('_run', ''), label: msg || d.label || event.event_type.replace(/_/g, ' '), status: d.status || (d.exit_code && d.exit_code !== 0 ? 'failed' : 'completed'), timestamp: event.timestamp, duration_ms: d.duration_ms, metadata: d }} />
    case 'action_failed':
    case 'plan_validation_failed':
      return <AgentErrorBlock title={msg || event.event_type.replace(/_/g, ' ')} body={d.error || d.reason} />
    case 'action_blocked':
    case 'decision_prompt':
      return <DecisionPromptCard question={d.question || msg || 'Action blocked'} options={d.options} status={d.status || 'waiting'} />
    case 'commit_created':
      return <CommitCard hash={d.commit_hash || d.hash || ''} message={d.commit_message || msg || 'Commit created'} branch={d.branch} />
    case 'pr_created':
    case 'pr_merged':
      return <PullRequestCard number={d.pr_number || 0} title={d.pr_title || msg || 'Pull request'} url={d.pr_url || d.url} status={event.event_type === 'pr_merged' ? 'merged' : 'open'} />
    case 'branch_pushed':
      return <div className="as-branch-pushed"><Upload size={14} /><span>Pushed branch </span><code className="as-git-branch">{d.branch || 'unknown'}</code>{d.url && <a href={d.url} target="_blank" rel="noopener" className="as-branch-repo"><ExternalLink size={14} /></a>}</div>
    default:
      return msg ? <AgentMessage content={msg} timestamp={event.timestamp} eventId={key} /> : null
  }
}

function WorklogPanel({ transcript }: { transcript: TranscriptData }) {
  return <div className="as-worklog-panel">{transcript.headline && <div className="wl-headline">{transcript.headline}</div>}{(transcript.working_duration_ms > 0 || transcript.additions > 0 || transcript.deletions > 0 || transcript.tasks_created > 0) && <div className="wl-summary-bar">{transcript.working_duration_ms > 0 && <span className="wl-duration"><Clock size={12} /> Working for {formatDuration(transcript.working_duration_ms)}</span>}{(transcript.additions > 0 || transcript.deletions > 0) && <span className="wl-diff-stat"><span className="wl-additions">+{transcript.additions}</span><span className="wl-deletions">-{transcript.deletions}</span></span>}{transcript.tasks_created > 0 && <span className="wl-tasks-count">Created {transcript.tasks_created} tasks</span>}</div>}{transcript.items.length === 0 && !transcript.headline ? <div className="as-empty"><p>No worklog entries yet.</p></div> : transcript.items.map((item, i) => <ToolRow key={`${item.timestamp}-${i}`} item={item} />)}{transcript.validation.overall !== 'not_run' && <div className={`wl-validation wl-validation-${transcript.validation.overall}`}>{transcript.validation.overall === 'passed' ? <CheckCircle size={14} /> : transcript.validation.overall === 'failed' ? <XCircle size={14} /> : <AlertTriangle size={14} />} Validation {transcript.validation.overall}</div>}</div>
}

function ChangesPanel({ transcript, events }: { transcript: TranscriptData; events: SessionEvent[] }) {
  const changes = useMemo(() => {
    const map = new Map<string, { path: string; additions: number; deletions: number }>()
    for (const item of transcript.items) {
      const path = item.metadata?.path
      if (item.kind === 'edit' && path) {
        const current = map.get(path) || { path, additions: 0, deletions: 0 }
        current.additions += item.metadata?.additions || 0
        current.deletions += item.metadata?.deletions || 0
        map.set(path, current)
      }
    }
    for (const event of events) {
      const d = event.data || {}
      const path = d.path
      if (event.event_type === 'file_edited' && path && !map.has(path)) map.set(path, { path, additions: d.additions || 0, deletions: d.deletions || 0 })
    }
    return Array.from(map.values())
  }, [transcript.items, events])
  if (!changes.length) return <div className="as-empty"><p>No changed files reported yet.</p></div>
  return <div className="as-changes-panel">{changes.map(change => <div key={change.path} className="as-change-file"><FileText size={14} /><span>{basename(change.path)}</span><code>{change.path}</code><span className="as-diff-add">+{change.additions}</span><span className="as-diff-del">-{change.deletions}</span></div>)}</div>
}

function DesktopPanel() {
  const [config, setConfig] = useState<RemoteDesktopConfig | null>(null)
  const [frameSrc, setFrameSrc] = useState('')
  const [status, setStatus] = useState('Loading desktop status...')
  const openDesktop = useCallback(async () => {
    if (!config?.enabled) return
    if (!config.auto_login) { setFrameSrc(config.url); return }
    setStatus('Signing in...')
    try {
      const session = await fetchJson<GuacamoleSession>('/v2/remote-desktop/token', { method: 'POST' })
      localStorage.setItem('GUAC_AUTH', JSON.stringify({ authToken: session.authToken, username: session.username, dataSource: session.dataSource, availableDataSources: session.availableDataSources }))
      setFrameSrc(session.connection_url || config.url)
      setStatus('Signed in')
    } catch (err) {
      setStatus(`Auto-login failed: ${(err as Error).message}`)
      setFrameSrc(config.url)
    }
  }, [config])
  useEffect(() => { fetchJson<RemoteDesktopConfig>('/v2/remote-desktop/config').then(data => { setConfig(data); setStatus(data.enabled ? 'Desktop ready' : 'Remote desktop disabled') }).catch(err => setStatus((err as Error).message)) }, [])
  return <div className="as-desktop-panel">{!config?.enabled ? <div className="as-empty"><p>{status}</p></div> : frameSrc ? <iframe title="Remote Desktop" src={frameSrc} className="remote-frame" allow="fullscreen; clipboard-read; clipboard-write" allowFullScreen /> : <div className="as-empty"><p>{status}</p><button className="as-action-btn" onClick={openDesktop}><Monitor size={14} /> Open Remote Desktop</button></div>}</div>
}

function TimelineScrubber({ timeline, selectedPointId, followLive, onSelectPoint, onPrev, onNext, onGoLive, onGoEnd }: { timeline: TimelineData; selectedPointId?: string; followLive: boolean; onSelectPoint: (point: TimelinePoint) => void; onPrev: () => void; onNext: () => void; onGoLive: () => void; onGoEnd: () => void }) {
  const total = Math.max(1, timeline.duration_ms || timeline.points[timeline.points.length - 1]?.offsetMs || 1)
  return <div className="as-scrubber"><button className="as-scrubber-btn" title="Previous event" onClick={onPrev}><ChevronLeft size={14} /></button><div className="as-scrubber-track">{timeline.segments.map(seg => <div key={seg.id} className={`as-scrubber-seg ${seg.desktopActive ? 'as-seg-active' : 'as-seg-inactive'}`} style={{ width: `${Math.max(1, ((seg.endOffsetMs - seg.startOffsetMs) / total) * 100)}%` }} />)}{timeline.points.filter(p => ['prompt', 'action', 'error', 'pr'].includes(p.kind)).map(point => <button key={point.id} className={`as-scrubber-marker ${point.id === selectedPointId ? 'as-marker-selected' : ''} as-marker-${point.kind}`} title={`${timeLabel(point.timestamp)} ${point.title}`} style={{ left: `${Math.min(100, Math.max(0, (point.offsetMs / total) * 100))}%` }} onClick={() => onSelectPoint(point)} />)}</div><button className="as-scrubber-btn" title="Next event" onClick={onNext}><ChevronRight size={14} /></button><button className={followLive ? 'as-scrubber-live' : 'as-scrubber-btn as-scrubber-golive'} title="Live" onClick={onGoLive}>{followLive && <span className="as-live-pip" />}<Monitor size={14} /> Live</button><button className="as-scrubber-btn" title="Go to end" onClick={onGoEnd}><SkipForward size={14} /></button></div>
}

function RightPane({ events, transcript, timeline, style }: { events: SessionEvent[]; transcript: TranscriptData; timeline: TimelineData; style?: CSSProperties }) {
  const [activeTab, setActiveTab] = useState<'worklog' | 'changes' | 'desktop'>('worklog')
  const [collapsed, setCollapsed] = useState(false)
  const [selectedPointId, setSelectedPointId] = useState<string | undefined>()
  const [followLive, setFollowLive] = useState(true)
  const selectedIndex = selectedPointId ? timeline.points.findIndex(point => point.id === selectedPointId) : -1
  const selectPoint = (point: TimelinePoint) => { setSelectedPointId(point.id); setFollowLive(false); if (point.kind === 'change') setActiveTab('changes'); if (point.desktopActive) setActiveTab('desktop') }
  const goLive = () => { setSelectedPointId(undefined); setFollowLive(true) }
  const prev = () => { const points = timeline.points.filter(p => ['prompt', 'action', 'error', 'pr', 'change'].includes(p.kind)); const current = selectedIndex >= 0 ? timeline.points[selectedIndex].offsetMs : Number.MAX_SAFE_INTEGER; const previous = points.filter(p => p.offsetMs < current).pop(); if (previous) selectPoint(previous) }
  const next = () => { const points = timeline.points.filter(p => ['prompt', 'action', 'error', 'pr', 'change'].includes(p.kind)); const current = selectedIndex >= 0 ? timeline.points[selectedIndex].offsetMs : -1; const nextPoint = points.find(p => p.offsetMs > current); if (nextPoint) selectPoint(nextPoint); else goLive() }
  if (collapsed) return <div className="as-right-collapsed"><button className="as-right-expand" onClick={() => setCollapsed(false)} title="Expand panel"><ChevronLeft size={16} /></button></div>
  return <aside className="as-right-pane" style={style}><div className="as-right-header"><div className="as-tab-strip"><button className={`as-tab ${activeTab === 'worklog' ? 'as-tab-active' : ''}`} onClick={() => setActiveTab('worklog')}>Worklog</button><button className={`as-tab ${activeTab === 'changes' ? 'as-tab-active' : ''}`} onClick={() => setActiveTab('changes')}>Changes</button><button className={`as-tab ${activeTab === 'desktop' ? 'as-tab-active' : ''}`} onClick={() => setActiveTab('desktop')}>Desktop</button></div><button className="as-right-collapse" onClick={() => setCollapsed(true)} title="Collapse"><ChevronRight size={14} /></button></div><div className="as-right-content">{activeTab === 'worklog' && <WorklogPanel transcript={transcript} />}{activeTab === 'changes' && <ChangesPanel transcript={transcript} events={events} />}{activeTab === 'desktop' && <DesktopPanel />}</div><TimelineScrubber timeline={timeline} selectedPointId={selectedPointId} followLive={followLive} onSelectPoint={selectPoint} onPrev={prev} onNext={next} onGoLive={goLive} onGoEnd={() => timeline.points.length && selectPoint(timeline.points[timeline.points.length - 1])} /></aside>
}

function ResizableBody({ children, events, transcript, timeline }: { children: ReactNode; events: SessionEvent[]; transcript: TranscriptData; timeline: TimelineData }) {
  const [rightWidth, setRightWidth] = useState(420)
  const [dragging, setDragging] = useState(false)
  const onMouseDown = useCallback((event: React.MouseEvent) => {
    event.preventDefault()
    setDragging(true)
    const startX = event.clientX
    const startWidth = rightWidth
    const onMove = (move: MouseEvent) => setRightWidth(Math.max(320, Math.min(760, startWidth - (move.clientX - startX))))
    const onUp = () => { setDragging(false); document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp) }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [rightWidth])
  return <div className="as-body"><div className="as-main-column">{children}</div><div className="as-resize-divider" onMouseDown={onMouseDown} title="Drag to resize" /><RightPane events={events} transcript={transcript} timeline={timeline} style={{ width: rightWidth }} />{dragging && <div style={{ position: 'fixed', inset: 0, zIndex: 9999, cursor: 'col-resize' }} />}</div>
}

function FloatingGuideComposer({ isRunning, onSend, onStop }: { isRunning: boolean; onSend: (instruction: string) => void; onStop: () => void }) {
  const [value, setValue] = useState('')
  const send = () => { const instruction = value.trim(); if (!instruction) return; onSend(instruction); setValue('') }
  return <div className="as-composer"><input className="as-composer-input" placeholder={isRunning ? 'Guide agent while it works' : 'Send a message'} value={value} onChange={event => setValue(event.target.value)} onKeyDown={event => event.key === 'Enter' && !event.shiftKey && send()} />{isRunning ? <button className="as-composer-stop" title="Stop" onClick={onStop}><Square size={14} fill="white" /></button> : <button className="as-composer-send" title="Send" onClick={send} disabled={!value.trim()}><Send size={16} /></button>}</div>
}

export default function AgentSessionPage({ sessionId, model, onBack }: { sessionId: string; model?: string; onBack?: () => void; sessions?: SessionRecord[]; onNavigateSession?: (id: string) => void }) {
  const [events, setEvents] = useState<SessionEvent[]>([])
  const [transcript, setTranscript] = useState<TranscriptData>(() => emptyTranscript(sessionId))
  const [timeline, setTimeline] = useState<TimelineData>({ points: [], segments: [], duration_ms: 1 })
  const [isRunning, setIsRunning] = useState(false)
  const [liveStatus, setLiveStatus] = useState('')
  const [error, setError] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)
  const lastSeqRef = useRef(0)

  const refreshDerived = useCallback(async () => {
    const [nextTranscript, nextTimeline] = await Promise.allSettled([
      fetchJson<TranscriptData>(`/sessions/${sessionId}/transcript`),
      fetchJson<TimelineData>(`/v2/sessions/${sessionId}/timeline`),
    ])
    if (nextTranscript.status === 'fulfilled') setTranscript(nextTranscript.value)
    if (nextTimeline.status === 'fulfilled') setTimeline({ points: nextTimeline.value.points || [], segments: nextTimeline.value.segments || [], duration_ms: nextTimeline.value.duration_ms || 1 })
  }, [sessionId])

  useEffect(() => {
    let cancelled = false
    lastSeqRef.current = 0
    setEvents([])
    setTranscript(emptyTranscript(sessionId))
    setTimeline({ points: [], segments: [], duration_ms: 1 })
    setError('')
    const loadInitial = async () => {
      try {
        const data = await fetchJson<{ events: SessionEvent[]; total: number }>(`/sessions/${sessionId}/events`)
        if (cancelled) return
        setEvents(data.events || [])
        lastSeqRef.current = data.total || data.events?.length || 0
        await refreshDerived()
      } catch (err) {
        if (!cancelled) setError((err as Error).message)
      }
    }
    const poll = async () => {
      while (!cancelled) {
        try {
          const data = await fetchJson<{ events: SessionEvent[]; total: number }>(`/sessions/${sessionId}/events/stream?after=${lastSeqRef.current}`)
          if (cancelled) return
          if (data.events?.length) {
            lastSeqRef.current = data.total || lastSeqRef.current + data.events.length
            setEvents(previous => {
              const seen = new Set(previous.map(event => event.event_id))
              const fresh = data.events.filter(event => !event.event_id || !seen.has(event.event_id))
              return fresh.length ? [...previous, ...fresh] : previous
            })
            const last = data.events[data.events.length - 1]
            const tool = last.data?.tool || last.data?.action_name
            if (['action_started', 'action_progress', 'plan_requested'].includes(last.event_type)) { setIsRunning(true); setLiveStatus(tool ? `Running: ${tool}` : truncate(eventMessage(last) || 'Working...', 48)) }
            if (['action_completed', 'action_failed', 'plan_completed', 'plan_cancelled'].includes(last.event_type)) { setIsRunning(false); setLiveStatus('') }
            refreshDerived()
          }
        } catch { /* transient polling failure */ }
        await new Promise(resolve => setTimeout(resolve, 1000))
      }
    }
    loadInitial()
    poll()
    return () => { cancelled = true }
  }, [sessionId, refreshDerived])

  useEffect(() => {
    const id = setInterval(() => fetchJson<{ state: string; message?: string }>(`/sessions/${sessionId}/state`).then(state => {
      const running = state.state === 'working' || state.state === 'running'
      setIsRunning(running)
      if (running && state.message) setLiveStatus(state.message)
    }).catch(() => undefined), 3000)
    return () => clearInterval(id)
  }, [sessionId])

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 200
    if (nearBottom) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [events])

  const sessionTitle = useMemo(() => {
    const firstPrompt = events.find(event => event.event_type === 'user_prompt_received')
    return firstPrompt ? truncate(eventMessage(firstPrompt), 60) : sessionId
  }, [events, sessionId])

  const handleSend = useCallback(async (instruction: string) => {
    setIsRunning(true)
    setLiveStatus('Sending...')
    setError('')
    try {
      await fetchJson(`/sessions/${sessionId}/chat`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ instruction, execution_mode: localStorage.getItem('settings.defaultExecutionMode') || 'finite' }) })
    } catch (err) {
      setError((err as Error).message)
      setIsRunning(false)
      setLiveStatus('')
    }
  }, [sessionId])

  const handleStop = useCallback(async () => {
    setLiveStatus('Stopping...')
    try { await fetchJson(`/sessions/${sessionId}/interrupt`, { method: 'POST' }) } catch (err) { setError((err as Error).message) }
    setIsRunning(false)
    setLiveStatus('Stopped')
  }, [sessionId])

  const nodes = useMemo(() => events.map((event, index) => ({ key: event.event_id || `${event.event_type}-${index}`, node: eventToNode(event), weight: event.event_type === 'user_prompt_received' || event.event_type.includes('failed') ? 'high' : 'medium' })).filter(item => item.node), [events])

  return <div className="as-page"><SessionTopBar title={sessionTitle} model={model || 'default agent model'} onBack={onBack} /><ResizableBody events={events} transcript={transcript} timeline={timeline}><div className="as-center-pane"><div className="as-scroll" ref={scrollRef}><div className="as-transcript"><div className="as-timeline">{error && <AgentErrorBlock title="Session UI error" body={error} />}{nodes.map(item => <div key={item.key} className={`as-timeline-item as-weight-${item.weight}`}>{item.node}</div>)}{events.length === 0 && !error && <div className="as-empty"><p>No events yet. Send a message to start working.</p></div>}</div></div></div><LiveAgentStatus status={liveStatus} animated={isRunning} /><FloatingGuideComposer isRunning={isRunning} onSend={handleSend} onStop={handleStop} /></div></ResizableBody></div>
}
