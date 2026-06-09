/**
 * AgentSessionPage — Devin-like live agent work transcript view.
 *
 * Renders a unified timeline of planning, file activity, commands,
 * browser actions, approvals, errors, and results for a single session.
 */
import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  ChevronDown, ChevronRight, ChevronLeft, ChevronUp, Check, X, Circle, Clock,
  AlertTriangle, File, FileText, FilePlus, FileX, Search, Terminal,
  GitBranch, GitPullRequest, GitCommit, GitMerge, Copy, Link, Monitor,
  Keyboard, MousePointer, Camera, Eye, Mic, Square, Plus, Send, BookOpen,
  RefreshCw, ExternalLink, Play, Minus, RotateCcw, Shield, Key, Loader,
  Lock, FlaskConical, Video, VideoOff, Upload, ArrowRight, ArrowLeft,
  CheckCircle, XCircle, MinusCircle, Zap, SkipForward,
  MessageSquare, Sparkles, Settings, Download, HelpCircle, MoreHorizontal,
  Layers, Hash,
} from 'lucide-react'

// ─── types ────────────────────────────────────────────────────────────────────

interface SessionEvent {
  event_type: string
  session_id: string
  data: Record<string, any>
  event_id: string
  timestamp: string
  sequence: number
}

interface RepoRef {
  provider: string
  owner: string
  repo: string
}

type PlanStepStatus = 'pending' | 'active' | 'completed' | 'failed' | 'blocked' | 'skipped'

interface PlanStep {
  id: string
  index: number
  title: string
  status: PlanStepStatus
}

// ─── helpers ──────────────────────────────────────────────────────────────────

function generateUUID(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = (Math.random() * 16) | 0
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
  })
}

function formatDuration(ms: number): string {
  const secs = Math.floor(ms / 1000)
  if (secs < 60) return `${secs}s`
  const mins = Math.floor(secs / 60)
  const rem = secs % 60
  if (mins < 60) return rem > 0 ? `${mins}m ${rem}s` : `${mins}m`
  const hrs = Math.floor(mins / 60)
  return `${hrs}h ${mins % 60}m`
}

function timeAgo(ts: string): string {
  try {
    const d = new Date(ts)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch { return '' }
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n) + '…' : s
}

const API = '/api'
const CONTROL_API = window.location.port === '5173'
  ? `${window.location.protocol}//${window.location.hostname}:9877/api`
  : API

// ─── sub-components ───────────────────────────────────────────────────────────

/* TopBar — session title + model badge */
function SessionTopBar({ title, model }: { title: string; model: string }) {
  return (
    <div className="as-topbar">
      <span className="as-topbar-title">{title || 'Agent Session'}</span>
      {model && <span className="as-model-badge">{model}</span>}
    </div>
  )
}

/* Workspace Sidebar — persistent left nav per spec 3 */
interface SidebarSession {
  id: string
  status: string
  repo_path: string
  created_at: string
  title?: string
}

function WorkspaceSidebar({
  sessions,
  activeSessionId,
  workspaceName,
  onNavigate,
  collapsed,
  onToggle,
}: {
  sessions: SidebarSession[]
  activeSessionId: string
  workspaceName: string
  onNavigate?: (sessionId: string) => void
  collapsed: boolean
  onToggle: () => void
}) {
  const [search, setSearch] = useState('')
  const [navActive, setNavActive] = useState('sessions')

  const navItems = [
    { key: 'sessions', label: 'Sessions', icon: <Layers size={16} /> },
    { key: 'ask', label: 'Ask', icon: <MessageSquare size={16} /> },
    { key: 'wiki', label: 'Wiki', icon: <BookOpen size={16} /> },
    { key: 'review', label: 'Review', icon: <Eye size={16} /> },
    { key: 'automations', label: 'Automations', icon: <Sparkles size={16} />, badge: 'Beta' },
  ]

  const filteredSessions = sessions.filter(s => {
    if (!search) return true
    const label = s.title || s.repo_path?.split('/').pop() || s.id
    return label.toLowerCase().includes(search.toLowerCase())
  })

  const relativeTime = (iso: string) => {
    const diff = Date.now() - new Date(iso).getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 1) return 'just now'
    if (mins < 60) return `${mins}m ago`
    const hrs = Math.floor(mins / 60)
    if (hrs < 24) return `${hrs}h ago`
    const days = Math.floor(hrs / 24)
    return `${days}d ago`
  }

  if (collapsed) {
    return (
      <div className="as-sidebar as-sidebar-collapsed">
        <button className="as-sidebar-toggle" onClick={onToggle} title="Expand sidebar">
          <ChevronRight size={16} />
        </button>
        <div className="as-sidebar-collapsed-nav">
          {navItems.map(n => (
            <button
              key={n.key}
              className={`as-sidebar-icon-btn ${navActive === n.key ? 'active' : ''}`}
              onClick={() => { setNavActive(n.key); onToggle() }}
              title={n.label}
            >
              {n.icon}
            </button>
          ))}
        </div>
        <div className="as-sidebar-collapsed-footer">
          <button className="as-sidebar-icon-btn" title="Settings"><Settings size={16} /></button>
        </div>
      </div>
    )
  }

  return (
    <div className="as-sidebar">
      {/* Workspace header */}
      <div className="as-sidebar-header">
        <div className="as-workspace-id">
          <div className="as-workspace-avatar">
            {workspaceName.charAt(0).toUpperCase()}
          </div>
          <span className="as-workspace-name">{workspaceName}</span>
          <ChevronDown size={14} className="as-workspace-chevron" />
        </div>
        <button className="as-sidebar-toggle" onClick={onToggle} title="Collapse sidebar">
          <ChevronLeft size={16} />
        </button>
      </div>

      {/* Primary nav */}
      <nav className="as-sidebar-nav">
        {navItems.map(n => (
          <button
            key={n.key}
            className={`as-nav-item ${navActive === n.key ? 'active' : ''}`}
            onClick={() => setNavActive(n.key)}
          >
            {n.icon}
            <span>{n.label}</span>
            {n.badge && <span className="as-nav-badge">{n.badge}</span>}
          </button>
        ))}
      </nav>

      {/* Sessions list */}
      <div className="as-sidebar-sessions">
        <div className="as-sessions-header">
          <span className="as-sessions-label">Recent</span>
          <div className="as-sessions-actions">
            <button className="as-sidebar-icon-btn" title="Search" onClick={() => {}}>
              <Search size={14} />
            </button>
            <button className="as-sidebar-icon-btn" title="New session">
              <Plus size={14} />
            </button>
            <button className="as-sidebar-icon-btn" title="More">
              <MoreHorizontal size={14} />
            </button>
          </div>
        </div>

        {/* Search input */}
        <div className="as-sessions-search">
          <Search size={12} />
          <input
            className="as-sessions-search-input"
            placeholder="Search sessions..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>

        <div className="as-sessions-list">
          {filteredSessions.map(s => {
            const label = s.title || s.repo_path?.split('/').pop() || s.id
            const isActive = s.id === activeSessionId
            const isLive = s.status === 'running'
            return (
              <div
                key={s.id}
                className={`as-session-row ${isActive ? 'active' : ''}`}
                onClick={() => onNavigate?.(s.id)}
              >
                <div className="as-session-row-top">
                  <span className="as-session-name">{truncate(label, 28)}</span>
                  {isLive && <span className="as-live-dot" />}
                </div>
                <div className="as-session-row-meta">
                  <span className="as-session-time">{relativeTime(s.created_at)}</span>
                  {s.repo_path && (
                    <span className="as-session-repo">
                      <GitBranch size={10} />
                      {s.repo_path.split('/').pop()}
                    </span>
                  )}
                </div>
              </div>
            )
          })}
          {filteredSessions.length === 0 && (
            <div className="as-sessions-empty">No sessions found.</div>
          )}
        </div>
      </div>

      {/* Footer */}
      <div className="as-sidebar-footer">
        <button className="as-nav-item">
          <Settings size={16} />
          <span>Settings</span>
        </button>
        <button className="as-sidebar-icon-btn" title="Export"><Download size={16} /></button>
        <button className="as-sidebar-icon-btn" title="Help"><HelpCircle size={16} /></button>
      </div>
    </div>
  )
}

/* Repo pill */
function RepoAttachmentPill({ owner, repo }: { owner: string; repo: string }) {
  return (
    <div className="as-repo-pill">
      <div className="as-repo-pill-icon">
        <GitBranch size={14} />
      </div>
      <span>{owner}/{repo}</span>
    </div>
  )
}

/* Message action bar */
function MessageActionBar({ timestamp }: { timestamp?: string }) {
  return (
    <div className="as-msg-actions">
      <button className="as-icon-btn" title="Open source context"><GitBranch size={14} /></button>
      <button className="as-icon-btn" title="Copy message"><Copy size={14} /></button>
      <button className="as-icon-btn" title="Copy link"><Link size={14} /></button>
      {timestamp && <span className="as-msg-time">{timeAgo(timestamp)}</span>}
    </div>
  )
}

/* User prompt message */
function UserPromptMessage({
  content, repos, timestamp, authorInitial,
}: {
  content: string; repos: RepoRef[]; timestamp?: string; authorInitial?: string
}) {
  const [expanded, setExpanded] = useState(false)
  const needsCollapse = content.length > 400

  return (
    <div className="as-user-prompt-row">
      <div className={`as-user-prompt ${!expanded && needsCollapse ? 'as-collapsed' : ''}`}>
        <div className="as-prompt-md">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
        </div>
        {needsCollapse && !expanded && (
          <div className="as-prompt-fade" onClick={() => setExpanded(true)}>
            <ChevronDown size={16} />
          </div>
        )}
        {needsCollapse && expanded && (
          <button className="as-prompt-collapse-btn" onClick={() => setExpanded(false)}>
            Collapse
          </button>
        )}
      </div>
      {repos.length > 0 && (
        <div className="as-repo-pills">
          {repos.map(r => <RepoAttachmentPill key={`${r.owner}/${r.repo}`} owner={r.owner} repo={r.repo} />)}
        </div>
      )}
      <MessageActionBar timestamp={timestamp} />
      <div className="as-user-avatar">{authorInitial || 'U'}</div>
    </div>
  )
}

/* Knowledge access row */
function KnowledgeAccessRow({ count, items }: { count: number; items?: string[] }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="as-knowledge-row" onClick={() => setOpen(!open)}>
      <BookOpen size={14} className="as-knowledge-icon" />
      <span>Accessed knowledge ({count})</span>
      {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      {open && items && items.length > 0 && (
        <div className="as-knowledge-list" onClick={e => e.stopPropagation()}>
          {items.map((it, i) => <div key={i} className="as-knowledge-item">{i + 1}. {it}</div>)}
        </div>
      )}
    </div>
  )
}

/* Agent message */
function AgentMessage({ content, timestamp }: { content: string; timestamp?: string }) {
  return (
    <div className="as-agent-msg">
      <div className="as-agent-msg-text">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      </div>
      {timestamp && <span className="as-msg-time">{timeAgo(timestamp)}</span>}
    </div>
  )
}

/* Work segment header */
function WorkSegmentHeader({
  expanded, duration, additions, deletions, onToggle,
}: {
  expanded: boolean; duration: string; additions?: number; deletions?: number
  onToggle: () => void
}) {
  return (
    <div className="as-segment-header" onClick={onToggle}>
      {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      <span className="as-segment-label">Worked for {duration}</span>
      {(additions !== undefined && additions > 0) && <span className="as-diff-add">+{additions}</span>}
      {(deletions !== undefined && deletions > 0) && <span className="as-diff-del">−{deletions}</span>}
    </div>
  )
}

/* Attachment card */
function AttachmentCard({ filename, size, icon }: { filename: string; size?: string; icon?: string }) {
  return (
    <div className="as-attachment">
      <FileText size={20} className="as-attachment-icon" />
      <div className="as-attachment-info">
        <span className="as-attachment-name">{filename}</span>
        {size && <span className="as-attachment-size">{size}</span>}
      </div>
    </div>
  )
}

/* Execution plan card */
function ExecutionPlanCard({
  steps, currentIndex, total,
}: {
  steps: PlanStep[]; currentIndex: number; total: number
}) {
  const currentTitle = steps[currentIndex]?.title || ''
  return (
    <div className="as-plan-card">
      <div className="as-plan-header">
        <span className="as-plan-counter">{currentIndex + 1}/{total}</span>
        <span className="as-plan-current">{currentTitle}</span>
      </div>
      <div className="as-plan-title-row">Execution plan</div>
      <div className="as-plan-steps">
        {steps.map((step) => (
          <div key={step.id} className={`as-plan-step as-step-${step.status}`}>
            <span className="as-step-icon">
              {step.status === 'completed' && <Check size={14} />}
              {step.status === 'active' && <Loader size={14} className="as-spin" />}
              {step.status === 'failed' && <X size={14} />}
              {step.status === 'blocked' && <Shield size={14} />}
              {step.status === 'skipped' && <Minus size={14} />}
              {step.status === 'pending' && <Circle size={12} />}
            </span>
            <span className="as-step-label">{step.title}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/* Thought segment */
function ThoughtSegment({
  duration, title, body,
}: {
  duration?: number; title: string; body: string
}) {
  const [open, setOpen] = useState(false)
  return (
    <div className="as-thought">
      <div className="as-thought-header" onClick={() => setOpen(!open)}>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <span className="as-thought-label">
          Thought{duration ? ` for ${formatDuration(duration)}` : ''}
        </span>
      </div>
      {open && (
        <div className="as-thought-body">
          {title && <div className="as-thought-title">{title}</div>}
          <div className="as-thought-text">{body}</div>
        </div>
      )}
    </div>
  )
}

/* File activity row */
function FileActivityRow({
  kind, file, ranges, additions, deletions, summary,
}: {
  kind: 'read' | 'edited' | 'created' | 'deleted' | 'searched' | 'executed'
  file: string; ranges?: { start: number; end: number }[]
  additions?: number; deletions?: number; summary?: string
}) {
  const icons: Record<string, typeof File> = {
    read: Eye, edited: FileText, created: FilePlus,
    deleted: FileX, searched: Search, executed: Terminal,
  }
  const Icon = icons[kind] || File

  return (
    <div className="as-file-row">
      <Icon size={14} className="as-file-icon" />
      <span className="as-file-kind">{kind === 'read' ? 'Read' : kind === 'edited' ? 'Edited' : kind === 'created' ? 'Created' : kind === 'deleted' ? 'Deleted' : kind === 'searched' ? 'Searched' : 'Executed'}</span>
      <span className="as-file-pill">{file.split('/').pop()}</span>
      {ranges && ranges.length > 0 && (
        <span className="as-file-ranges">
          {ranges.map((r, i) => <span key={i}>{i > 0 && ', '}:{r.start}-{r.end}</span>)}
        </span>
      )}
      {additions !== undefined && additions > 0 && <span className="as-diff-add">+{additions}</span>}
      {deletions !== undefined && deletions > 0 && <span className="as-diff-del">−{deletions}</span>}
      {summary && <span className="as-file-summary">{summary}</span>}
    </div>
  )
}

/* Command activity row */
function CommandActivityRow({
  command, status, host, exitCode, duration,
}: {
  command: string; status: 'started' | 'completed' | 'failed'
  host?: string; exitCode?: number; duration?: number
}) {
  const [expanded, setExpanded] = useState(false)
  const isLong = command.length > 80
  const preview = isLong ? command.slice(0, 80) + '…' : command

  return (
    <div className={`as-cmd-row as-cmd-${status}`} onClick={() => isLong && setExpanded(!expanded)}>
      <Terminal size={14} className="as-cmd-icon" />
      {host && <span className="as-cmd-host">{host}</span>}
      <code className="as-cmd-text">{expanded ? command : preview}</code>
      {exitCode !== undefined && exitCode !== 0 && (
        <span className="as-cmd-exit">exit {exitCode}</span>
      )}
      {duration !== undefined && <span className="as-cmd-dur">{formatDuration(duration)}</span>}
    </div>
  )
}

/* Browser activity row */
function BrowserActivityRow({
  action, value, coordinates, duration,
}: {
  action: 'pressed_key' | 'typed_text' | 'clicked' | 'double_clicked' | 'waited' | 'screenshot'
  value?: string; coordinates?: { x: number; y: number }; duration?: number
}) {
  const icons: Record<string, typeof Keyboard> = {
    pressed_key: Keyboard, typed_text: FileText, clicked: MousePointer,
    double_clicked: MousePointer, waited: Clock, screenshot: Camera,
  }
  const Icon = icons[action] || Circle
  const labels: Record<string, string> = {
    pressed_key: 'Pressed key', typed_text: 'Typed text', clicked: 'Clicked',
    double_clicked: 'Double-clicked', waited: 'Waited', screenshot: 'Took screenshot',
  }

  return (
    <div className="as-browser-row">
      <Icon size={12} className="as-browser-icon" />
      <span className="as-browser-label">{labels[action] || action}</span>
      {value && action === 'pressed_key' && <code className="as-browser-val">{value}</code>}
      {value && action === 'typed_text' && <span className="as-browser-val">[redacted]</span>}
      {coordinates && <span className="as-browser-coords">({coordinates.x}, {coordinates.y})</span>}
      {duration !== undefined && action === 'waited' && <span className="as-browser-dur">{formatDuration(duration)}s</span>}
    </div>
  )
}

/* Decision prompt card */
function DecisionPromptCard({
  question, options, selectedOption, status,
}: {
  question: string; options?: string[]; selectedOption?: string
  status: 'waiting' | 'answered' | 'expired'
}) {
  return (
    <div className={`as-decision-card as-decision-${status}`}>
      <div className="as-decision-q">Q: {question}</div>
      {selectedOption && (
        <div className="as-decision-answer">{selectedOption}</div>
      )}
      {status === 'waiting' && options && options.length > 0 && (
        <div className="as-decision-options">
          {options.map((opt, i) => (
            <button key={i} className="as-decision-opt-btn">{opt}</button>
          ))}
        </div>
      )}
    </div>
  )
}

/* Credential request card */
function CredentialRequestCard({
  secretName, purpose, timeoutSeconds, status,
}: {
  secretName: string; purpose?: string
  timeoutSeconds?: number; status: 'waiting' | 'provided' | 'expired' | 'cancelled'
}) {
  return (
    <div className={`as-cred-card as-cred-${status}`}>
      <Key size={16} className="as-cred-icon" />
      <div className="as-cred-body">
        <div className="as-cred-name">Credentials requested: <strong>{secretName}</strong></div>
        {purpose && <div className="as-cred-purpose">{purpose}</div>}
        <div className="as-cred-status">
          {status === 'waiting' && timeoutSeconds && `Waiting for auth key (${timeoutSeconds}s)`}
          {status === 'provided' && 'Secret received and redacted'}
          {status === 'expired' && 'Request expired'}
          {status === 'cancelled' && 'Request cancelled'}
        </div>
      </div>
    </div>
  )
}

/* Agent error block */
function AgentErrorBlock({
  title, body, suggestedAction, recoverable,
}: {
  title: string; body?: string; suggestedAction?: string; recoverable?: boolean
}) {
  return (
    <div className="as-error-block">
      <div className="as-error-header">
        <AlertTriangle size={16} />
        <span>Agent error</span>
      </div>
      <div className="as-error-title">{title}</div>
      {body && <div className="as-error-body">{body}</div>}
      {suggestedAction && (
        <div className="as-error-action">Suggested: {suggestedAction}</div>
      )}
    </div>
  )
}

/* Inline action button (Open Desktop, Open PR, etc.) */
function InlineActionButton({
  icon, label, onClick,
}: {
  icon: 'Monitor' | 'GitPullRequest' | 'ExternalLink' | 'Play' | 'RotateCcw' | 'Square'
  label: string; onClick?: () => void
}) {
  const icons: Record<string, typeof Monitor> = {
    Monitor, GitPullRequest, ExternalLink, Play, RotateCcw, Square,
  }
  const Icon = icons[icon] || ExternalLink
  return (
    <button className="as-action-btn" onClick={onClick}>
      <Icon size={14} />
      <span>{label}</span>
    </button>
  )
}

/* Commit card */
function CommitCard({ hash, message, branch }: { hash: string; message: string; branch?: string }) {
  return (
    <div className="as-commit-card">
      <GitCommit size={16} className="as-commit-icon" />
      <div className="as-commit-body">
        <code className="as-commit-hash">{hash.slice(0, 8)}</code>
        <span className="as-commit-msg">{message}</span>
        {branch && <span className="as-commit-branch">{branch}</span>}
      </div>
    </div>
  )
}

/* Pull request card */
function PullRequestCard({
  number, title, url, status,
}: {
  number: number; title: string; url?: string; status?: string
}) {
  return (
    <div className="as-pr-card">
      <GitPullRequest size={16} className="as-pr-icon" />
      <div className="as-pr-body">
        <span className="as-pr-number">#{number}</span>
        <span className="as-pr-title">{title}</span>
        {status && <span className={`as-pr-status as-pr-${status}`}>{status}</span>}
      </div>
      {url && (
        <a href={url} target="_blank" rel="noopener" className="as-pr-link">
          <ExternalLink size={14} />
        </a>
      )}
    </div>
  )
}

/* Live agent status */
function LiveAgentStatus({ status, animated }: { status: string; animated?: boolean }) {
  if (!status) return null
  return (
    <div className="as-live-status">
      {animated && <Loader size={14} className="as-spin" />}
      <span>{status}</span>
    </div>
  )
}

/* Secret chip — redacted secret variable */
function SecretChip({ label }: { label: string }) {
  return (
    <span className="as-secret-chip">
      <Lock size={11} />
      <span>{label}</span>
    </span>
  )
}

/* Recording event row */
function RecordingEventRow({ status, duration }: {
  status: 'started' | 'stopped' | 'failed'; duration?: number
}) {
  return (
    <div className={`as-recording-row as-rec-${status}`}>
      {status === 'started' && <Video size={14} className="as-rec-icon as-rec-dot" />}
      {status === 'stopped' && <VideoOff size={14} className="as-rec-icon" />}
      {status === 'failed' && <XCircle size={14} className="as-rec-icon" />}
      <span className="as-rec-label">
        {status === 'started' ? 'Recording started' : status === 'stopped' ? 'Stopped recording' : 'Recording failed'}
      </span>
      {duration !== undefined && <span className="as-rec-dur">{formatDuration(duration)}</span>}
    </div>
  )
}

/* Git activity row */
function GitActivityRow({ action, commandPreview, message, branch, remote }: {
  action: 'status_diff' | 'commit' | 'push' | 'merge' | 'rebase' | 'pull' | 'checkout'
  commandPreview?: string; message?: string; branch?: string; remote?: string
}) {
  const icons: Record<string, typeof GitCommit> = {
    status_diff: GitBranch, commit: GitCommit, push: Upload,
    merge: GitMerge, rebase: RefreshCw, pull: ArrowRight, checkout: GitBranch,
  }
  const Icon = icons[action] || GitCommit
  const labels: Record<string, string> = {
    status_diff: 'Status/diff', commit: 'Committed', push: 'Pushed',
    merge: 'Merged', rebase: 'Rebased', pull: 'Pulled', checkout: 'Checked out',
  }

  return (
    <div className="as-git-row">
      <Icon size={14} className="as-git-icon" />
      <span className="as-git-action">{labels[action] || action}</span>
      {message && <span className="as-git-msg">{truncate(message, 60)}</span>}
      {branch && <code className="as-git-branch">{branch}</code>}
      {remote && <span className="as-git-remote">→ {remote}</span>}
      {commandPreview && !message && <code className="as-cmd-text">{truncate(commandPreview, 70)}</code>}
    </div>
  )
}

/* Branch pushed row */
function BranchPushedRow({ branch, repo, url }: {
  branch: string; repo: string; url?: string
}) {
  return (
    <div className="as-branch-pushed">
      <Upload size={14} className="as-branch-icon" />
      <span>Pushed branch </span>
      <code className="as-git-branch">{branch}</code>
      <span> to </span>
      {url ? (
        <a href={url} target="_blank" rel="noopener" className="as-branch-repo">{repo}</a>
      ) : (
        <span className="as-branch-repo">{repo}</span>
      )}
    </div>
  )
}

/* Plan revision card */
function PlanRevisionCard({ reason, triggeredBy, newSteps }: {
  reason: string; triggeredBy?: string; newSteps: string[]
}) {
  const [open, setOpen] = useState(true)
  return (
    <div className="as-plan-revision">
      <div className="as-plan-revision-header" onClick={() => setOpen(!open)}>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <RefreshCw size={14} className="as-revision-icon" />
        <span className="as-revision-label">Plan revised</span>
        {triggeredBy && <span className="as-revision-trigger">{triggeredBy}</span>}
      </div>
      <div className="as-revision-reason">{reason}</div>
      {open && (
        <div className="as-revision-steps">
          {newSteps.map((step, i) => (
            <div key={i} className="as-revision-step">
              <Circle size={10} className="as-revision-step-icon" />
              <span>{step}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/* User override card */
function UserOverrideCard({ command, skippedSteps, riskFlags }: {
  command: string; skippedSteps?: string[]; riskFlags?: string[]
}) {
  return (
    <div className="as-override-card">
      <div className="as-override-header">
        <SkipForward size={14} className="as-override-icon" />
        <span>User override: <strong>{command}</strong></span>
      </div>
      {skippedSteps && skippedSteps.length > 0 && (
        <div className="as-override-skipped">
          {skippedSteps.map((s, i) => (
            <span key={i} className="as-override-skip-pill">
              <Minus size={10} /> {s}
            </span>
          ))}
        </div>
      )}
      {riskFlags && riskFlags.length > 0 && (
        <div className="as-override-risks">
          {riskFlags.map((r, i) => (
            <span key={i} className="as-override-risk-pill">
              <AlertTriangle size={10} /> {r}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

/* Test report preparation block */
function TestReportPreparationBlock({ title, summary, artifacts, status }: {
  title?: string; summary?: string; status: 'preparing' | 'created' | 'attached' | 'skipped'
  artifacts?: { kind: string; count?: number; status?: string }[]
}) {
  return (
    <div className={`as-test-report as-test-report-${status}`}>
      <FlaskConical size={14} className="as-test-report-icon" />
      <div className="as-test-report-body">
        <div className="as-test-report-title">{title || 'Preparing test report'}</div>
        {summary && <div className="as-test-report-summary">{summary}</div>}
        {artifacts && artifacts.length > 0 && (
          <div className="as-test-report-artifacts">
            {artifacts.map((a, i) => (
              <span key={i} className="as-test-artifact-pill">
                {a.kind === 'screenshot' && <Camera size={11} />}
                {a.kind === 'recording' && <Video size={11} />}
                {a.kind !== 'screenshot' && a.kind !== 'recording' && <File size={11} />}
                {a.kind}{a.count ? ` (${a.count})` : ''}{a.status ? ` — ${a.status}` : ''}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

/* CI status row */
function CiStatusRow({ prNumber, status, message }: {
  prNumber: number; status: 'none' | 'pending' | 'passing' | 'failing' | 'cancelled' | 'unknown'
  message?: string
}) {
  const statusIcons: Record<string, typeof Circle> = {
    none: MinusCircle, pending: Loader, passing: CheckCircle,
    failing: XCircle, cancelled: XCircle, unknown: Circle,
  }
  const Icon = statusIcons[status] || Circle

  return (
    <div className={`as-ci-row as-ci-${status}`}>
      <Icon size={14} className={`as-ci-icon ${status === 'pending' ? 'as-spin' : ''}`} />
      <span>CI for PR #{prNumber}</span>
      <span className="as-ci-status-label">{status}</span>
      {message && <span className="as-ci-msg">{message}</span>}
    </div>
  )
}

/* Review action bar */
function ReviewActionBar({ label, actions }: {
  label?: string; actions: { label: string; kind: 'primary' | 'secondary'; onClick?: () => void }[]
}) {
  return (
    <div className="as-review-bar">
      {label && <span className="as-review-label">{label}</span>}
      <div className="as-review-actions">
        {actions.map((a, i) => (
          <button key={i} className={`as-review-btn as-review-${a.kind}`} onClick={a.onClick}>
            {a.label}
          </button>
        ))}
      </div>
    </div>
  )
}

/* Test mode event row */
function TestModeEventRow({ goal }: { goal: string }) {
  return (
    <div className="as-test-mode">
      <FlaskConical size={14} className="as-test-mode-icon" />
      <span>Entered test mode</span>
      {goal && <span className="as-test-mode-goal">— {goal}</span>}
    </div>
  )
}

// ─── right pane components ──────────────────────────────────────────────────

interface ArtifactTab {
  kind: 'worklog' | 'changes' | 'file' | 'pr' | 'desktop' | 'recording'
  label: string
  prNumber?: number
  filePath?: string
}

/* Artifact tab strip */
function ArtifactTabStrip({ tabs, activeIndex, onSelect }: {
  tabs: ArtifactTab[]; activeIndex: number; onSelect: (i: number) => void
}) {
  return (
    <div className="as-tab-strip">
      {tabs.map((tab, i) => (
        <button
          key={i}
          className={`as-tab ${i === activeIndex ? 'as-tab-active' : ''}`}
          onClick={() => onSelect(i)}
        >
          {tab.kind === 'pr' && <GitPullRequest size={12} />}
          {tab.kind === 'desktop' && <Monitor size={12} />}
          {tab.kind === 'file' && <File size={12} />}
          {tab.kind === 'recording' && <Video size={12} />}
          <span>{tab.label}</span>
        </button>
      ))}
    </div>
  )
}

/* Executed command panel for worklog */
function ExecutedCommandPanel({ command, output, host, exitCode }: {
  command: string; output?: string; host?: string; exitCode?: number
}) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div className="as-exec-panel">
      <div className="as-exec-header" onClick={() => setExpanded(!expanded)}>
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <Terminal size={14} />
        <span>Executed </span>
        <code className="as-exec-cmd">{truncate(command, 80)}</code>
        {exitCode !== undefined && exitCode !== 0 && <span className="as-cmd-exit">exit {exitCode}</span>}
      </div>
      {expanded && output && (
        <div className="as-exec-terminal">
          <div className="as-terminal-prompt">
            {host || 'ubuntu@devin-box'}:~$ {command}
          </div>
          <pre className="as-terminal-output">{output}</pre>
        </div>
      )}
    </div>
  )
}

/* File read inspector for worklog */
function FileReadInspector({ path, displayName, repo, lineStart, lineEnd, content }: {
  path: string; displayName?: string; repo?: string
  lineStart?: number; lineEnd?: number; content?: string
}) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div className="as-file-inspector">
      <div className="as-file-inspector-header" onClick={() => setExpanded(!expanded)}>
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <Eye size={14} />
        <span>Read </span>
        <code className="as-file-pill">{displayName || path.split('/').pop()}</code>
        {lineStart !== undefined && lineEnd !== undefined && (
          <span className="as-file-ranges">:{lineStart}-{lineEnd}</span>
        )}
        <button className="as-icon-btn" title="Copy" onClick={e => {
          e.stopPropagation()
          if (content) navigator.clipboard.writeText(content)
        }}><Copy size={12} /></button>
      </div>
      {expanded && (
        <div className="as-code-card">
          <div className="as-code-meta">
            <span className="as-code-path">{path}</span>
            {repo && <span className="as-code-repo">{repo}</span>}
          </div>
          <pre className="as-code-block">
            {content ? content.split('\n').map((line, i) => (
              <div key={i} className="as-code-line">
                <span className="as-line-num">{(lineStart || 1) + i}</span>
                <span className="as-line-text">{line}</span>
              </div>
            )) : <span className="as-code-placeholder">Content not available</span>}
          </pre>
        </div>
      )}
    </div>
  )
}

/* Changes panel — time-scoped change filter, file summary, diff cards */
interface FileChangeSummary {
  path: string; repo?: string; additions: number; deletions: number
}

interface DiffHunk {
  startLine: number; lines: { type: 'add' | 'del' | 'ctx'; text: string; num: number }[]
}

function ChangesPanel({ files, timeFilter, onClearFilter }: {
  files: FileChangeSummary[]
  timeFilter?: { startTime: string; endTime: string }
  onClearFilter?: () => void
}) {
  const [selectedFile, setSelectedFile] = useState<string | null>(null)

  return (
    <div className="as-changes-panel">
      {timeFilter && (
        <div className="as-changes-filter">
          <span>Showing changes from {timeAgo(timeFilter.startTime)}–{timeAgo(timeFilter.endTime)}</span>
          {onClearFilter && <button className="as-changes-clear" onClick={onClearFilter}>Clear filter</button>}
        </div>
      )}
      <div className="as-changes-list">
        {files.map((f, i) => (
          <div key={i}
            className={`as-changes-file ${selectedFile === f.path ? 'as-changes-file-selected' : ''}`}
            onClick={() => setSelectedFile(selectedFile === f.path ? null : f.path)}
          >
            <span className="as-changes-file-name">{f.path.split('/').pop()}</span>
            <span className="as-changes-file-path">{f.path}</span>
            <span className="as-changes-stats">
              {f.additions > 0 && <span className="as-diff-add">+{f.additions}</span>}
              {f.deletions > 0 && <span className="as-diff-del">−{f.deletions}</span>}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

/* Timeline scrubber minimap */
interface TimelineSegment {
  startTime: string; endTime: string; eventType: string; density: number
}

function TimelineScrubber({ segments, onJumpToEnd, onJumpToDesktop }: {
  segments: TimelineSegment[]
  onJumpToEnd?: () => void
  onJumpToDesktop?: () => void
}) {
  return (
    <div className="as-scrubber">
      <button className="as-scrubber-btn" title="Previous">
        <ArrowLeft size={14} />
      </button>
      <div className="as-scrubber-track">
        {segments.map((seg, i) => (
          <div
            key={i}
            className="as-scrubber-seg"
            style={{ flex: seg.density, opacity: Math.min(1, 0.3 + seg.density * 0.3) }}
            title={`${seg.eventType} (${timeAgo(seg.startTime)})`}
          />
        ))}
      </div>
      <button className="as-scrubber-btn" title="Next">
        <ArrowRight size={14} />
      </button>
      {onJumpToDesktop && (
        <button className="as-scrubber-btn" title="Go to live desktop" onClick={onJumpToDesktop}>
          <Monitor size={14} />
        </button>
      )}
      {onJumpToEnd && (
        <button className="as-scrubber-btn" title="Go to end" onClick={onJumpToEnd}>
          <SkipForward size={14} />
        </button>
      )}
    </div>
  )
}

/* Worklog panel — combines executed commands and file read inspectors */
function WorklogPanel({ events }: { events: SessionEvent[] }) {
  const worklogItems = useMemo(() => {
    const items: { key: string; component: React.ReactNode }[] = []
    for (let i = 0; i < events.length; i++) {
      const ev = events[i]
      const d = ev.data || {}
      const key = ev.event_id || `wl-${i}`
      if (ev.event_type === 'action_progress') {
        const tool = d.tool || ''
        if (tool === 'bash' || tool === 'execute_bash') {
          items.push({
            key,
            component: <ExecutedCommandPanel key={key}
              command={d.command || d.args_summary || ''}
              output={d.output}
              host={d.host}
              exitCode={d.exit_code}
            />,
          })
        } else if (tool === 'read_file' || (tool === 'str_replace_editor' && (d.args_summary || '').includes('view'))) {
          items.push({
            key,
            component: <FileReadInspector key={key}
              path={d.path || d.args_summary || ''}
              displayName={d.path?.split('/').pop()}
              repo={d.repo}
              lineStart={d.line_start}
              lineEnd={d.line_end}
              content={d.content || d.output}
            />,
          })
        }
      }
    }
    return items
  }, [events])

  if (worklogItems.length === 0) {
    return <div className="as-empty"><p>No worklog entries yet.</p></div>
  }

  return (
    <div className="as-worklog-panel">
      {worklogItems.map(item => (
        <div key={item.key} className="as-worklog-item">{item.component}</div>
      ))}
    </div>
  )
}

/* Right pane — artifact inspector */
function RightPane({ events, sessionId }: { events: SessionEvent[]; sessionId: string }) {
  const [activeTab, setActiveTab] = useState(0)
  const [collapsed, setCollapsed] = useState(false)

  // Build tabs from events
  const tabs = useMemo(() => {
    const t: ArtifactTab[] = [
      { kind: 'worklog', label: 'Worklog' },
      { kind: 'changes', label: 'Changes' },
    ]
    const prNums = new Set<number>()
    const files = new Set<string>()
    for (const ev of events) {
      if (ev.event_type === 'pr_created' && ev.data?.pr_number) {
        const n = ev.data.pr_number
        if (!prNums.has(n)) {
          prNums.add(n)
          t.push({ kind: 'pr', label: `PR #${n}`, prNumber: n })
        }
      }
      if (ev.event_type === 'action_progress' && ev.data?.path) {
        const fp = ev.data.path
        if (!files.has(fp)) {
          files.add(fp)
          if (files.size <= 3) {
            t.push({ kind: 'file', label: fp.split('/').pop() || fp, filePath: fp })
          }
        }
      }
    }
    t.push({ kind: 'desktop', label: 'Desktop' })
    return t
  }, [events])

  // Build file change summaries from events for changes tab
  const fileChanges = useMemo(() => {
    const changes: Record<string, FileChangeSummary> = {}
    for (const ev of events) {
      if (ev.event_type === 'action_progress') {
        const d = ev.data || {}
        const tool = d.tool || ''
        if (tool === 'str_replace_editor' || tool === 'write_file' || tool === 'edit_file') {
          const path = d.path || d.args_summary?.match(/path[=:]\s*["']?([^\s"',]+)/)?.[1] || ''
          if (path && !changes[path]) {
            changes[path] = { path, additions: d.additions || 0, deletions: d.deletions || 0 }
          } else if (path) {
            changes[path].additions += d.additions || 0
            changes[path].deletions += d.deletions || 0
          }
        }
      }
    }
    return Object.values(changes)
  }, [events])

  // Timeline segments for scrubber
  const segments = useMemo(() => {
    const segs: TimelineSegment[] = []
    const chunkSize = Math.max(1, Math.floor(events.length / 30))
    for (let i = 0; i < events.length; i += chunkSize) {
      const chunk = events.slice(i, i + chunkSize)
      if (chunk.length > 0) {
        segs.push({
          startTime: chunk[0].timestamp,
          endTime: chunk[chunk.length - 1].timestamp,
          eventType: chunk[0].event_type,
          density: chunk.length / chunkSize,
        })
      }
    }
    return segs
  }, [events])

  if (collapsed) {
    return (
      <div className="as-right-collapsed">
        <button className="as-right-expand" onClick={() => setCollapsed(false)} title="Expand panel">
          <ChevronLeft size={16} />
        </button>
      </div>
    )
  }

  return (
    <div className="as-right-pane">
      <div className="as-right-header">
        <ArtifactTabStrip tabs={tabs} activeIndex={activeTab} onSelect={setActiveTab} />
        <button className="as-right-collapse" onClick={() => setCollapsed(true)} title="Collapse">
          <ChevronRight size={14} />
        </button>
      </div>

      <div className="as-right-content">
        {tabs[activeTab]?.kind === 'worklog' && (
          <WorklogPanel events={events} />
        )}
        {tabs[activeTab]?.kind === 'changes' && (
          <ChangesPanel files={fileChanges} />
        )}
        {tabs[activeTab]?.kind === 'desktop' && (
          <div className="as-desktop-placeholder">
            <Monitor size={48} />
            <p>Live desktop view</p>
            <button className="as-action-btn" onClick={() => {}}>
              <Monitor size={14} /> <span>Go to live desktop</span>
            </button>
          </div>
        )}
        {tabs[activeTab]?.kind === 'pr' && (
          <div className="as-pr-placeholder">
            <GitPullRequest size={32} />
            <p>PR #{tabs[activeTab].prNumber} details</p>
          </div>
        )}
        {tabs[activeTab]?.kind === 'file' && (
          <div className="as-file-placeholder">
            <File size={32} />
            <p>{tabs[activeTab].filePath || tabs[activeTab].label}</p>
          </div>
        )}
      </div>

      <TimelineScrubber segments={segments} />
    </div>
  )
}

// ─── event → component mapping ───────────────────────────────────────────────

interface ParsedEvent {
  key: string
  weight: 'high' | 'medium' | 'low'
  component: React.ReactNode
}

function parseSessionEvents(events: SessionEvent[]): ParsedEvent[] {
  const parsed: ParsedEvent[] = []
  let segmentStart: number | null = null
  let segmentAdditions = 0
  let segmentDeletions = 0
  let segmentExpanded = true

  // Track plan steps from plan_generated
  let planSteps: PlanStep[] = []
  let planCurrentIndex = 0

  for (let i = 0; i < events.length; i++) {
    const ev = events[i]
    const key = ev.event_id || `ev-${i}`
    const d = ev.data || {}
    const msg = d.message || ''

    switch (ev.event_type) {
      case 'user_prompt_received': {
        // Extract repos from message or session context
        const repos: RepoRef[] = []
        const repoMatches = msg.match(/\b(\w+)\/(\w[\w-]+)\b/g) || []
        const seen = new Set<string>()
        for (const m of repoMatches) {
          if (!seen.has(m)) {
            const [owner, repo] = m.split('/')
            repos.push({ provider: 'github', owner, repo })
            seen.add(m)
          }
        }
        parsed.push({
          key, weight: 'high',
          component: <UserPromptMessage
            key={key} content={msg} repos={repos}
            timestamp={ev.timestamp} authorInitial="S"
          />,
        })
        break
      }

      case 'routing_decision_made':
        parsed.push({
          key, weight: 'high',
          component: <AgentMessage key={key} content={msg} timestamp={ev.timestamp} />,
        })
        break

      case 'plan_requested':
        parsed.push({
          key, weight: 'medium',
          component: <AgentMessage key={key}
            content={`Planning: ${d.prompt || msg || 'Requesting advisory plan...'}`}
            timestamp={ev.timestamp}
          />,
        })
        if (d.prompt) {
          parsed.push({
            key: key + '-prompt', weight: 'low',
            component: (
              <ThoughtSegment key={key + '-prompt'}
                title="Prompt sent to agent-core"
                body={d.prompt}
              />
            ),
          })
        }
        break

      case 'plan_generated': {
        // Parse plan steps from the response
        const plan = d.plan || d.steps || []
        if (Array.isArray(plan) && plan.length > 0) {
          planSteps = plan.map((s: any, idx: number) => ({
            id: s.id || `step-${idx}`,
            index: idx,
            title: s.title || s.action_name || s.description || `Step ${idx + 1}`,
            status: idx === 0 ? 'active' as PlanStepStatus : 'pending' as PlanStepStatus,
          }))
          planCurrentIndex = 0
          parsed.push({
            key, weight: 'high',
            component: <ExecutionPlanCard key={key}
              steps={planSteps} currentIndex={planCurrentIndex} total={planSteps.length}
            />,
          })
        } else {
          // Fallback: show as message
          parsed.push({
            key, weight: 'high',
            component: <AgentMessage key={key} content={`Plan generated: ${msg}`} timestamp={ev.timestamp} />,
          })
        }

        // Show LLM prompt if available
        if (d.llm_prompt) {
          parsed.push({
            key: key + '-llm', weight: 'low',
            component: (
              <ThoughtSegment key={key + '-llm'}
                title="DeepSeek API prompt"
                body={d.llm_prompt}
              />
            ),
          })
        }
        break
      }

      case 'plan_validation_failed':
        parsed.push({
          key, weight: 'high',
          component: <AgentErrorBlock key={key}
            title="Plan validation failed"
            body={msg}
            recoverable
          />,
        })
        break

      case 'action_started':
        if (segmentStart === null) {
          segmentStart = new Date(ev.timestamp).getTime()
        }
        parsed.push({
          key, weight: 'medium',
          component: <AgentMessage key={key} content={msg || 'Starting executor'} timestamp={ev.timestamp} />,
        })
        break

      case 'workspace_provisioned':
        parsed.push({
          key, weight: 'medium',
          component: <AgentMessage key={key}
            content={`Workspace provisioned: ${d.worktree_path || msg}`}
            timestamp={ev.timestamp}
          />,
        })
        break

      case 'action_progress': {
        const tool = d.tool || ''
        const args = d.args_summary || ''

        // File operations
        if (tool === 'read_file' || tool === 'str_replace_editor' && args.includes('view')) {
          const fileMatch = args.match(/path[=:]\s*["']?([^\s"',]+)/) || args.match(/([^\s,]+\.\w+)/)
          const rangeMatch = args.match(/(\d+)-(\d+)/)
          parsed.push({
            key, weight: 'medium',
            component: <FileActivityRow key={key}
              kind="read"
              file={fileMatch?.[1] || 'file'}
              ranges={rangeMatch ? [{ start: parseInt(rangeMatch[1]), end: parseInt(rangeMatch[2]) }] : undefined}
            />,
          })
        } else if (tool === 'str_replace_editor' || tool === 'write_file' || tool === 'edit_file') {
          const fileMatch = args.match(/path[=:]\s*["']?([^\s"',]+)/) || args.match(/([^\s,]+\.\w+)/)
          parsed.push({
            key, weight: 'medium',
            component: <FileActivityRow key={key}
              kind="edited"
              file={fileMatch?.[1] || 'file'}
            />,
          })
        } else if (tool === 'search' || tool === 'grep' || tool === 'find') {
          parsed.push({
            key, weight: 'medium',
            component: <FileActivityRow key={key} kind="searched" file={args || 'codebase'} />,
          })
        } else if (tool === 'bash' || tool === 'execute_bash') {
          // Command execution
          const cmd = d.command || args || msg
          parsed.push({
            key, weight: 'medium',
            component: <CommandActivityRow key={key}
              command={cmd}
              status="completed"
              host={cmd.includes('ssh') ? cmd.match(/ssh\s+\S+@([\d.]+)/)?.[1] : undefined}
            />,
          })
        } else if (tool === 'browser_action' || tool.startsWith('browser_')) {
          // Browser action
          const action = d.action || tool.replace('browser_', '')
          parsed.push({
            key, weight: 'low',
            component: <BrowserActivityRow key={key}
              action={action as any}
              value={d.value}
              coordinates={d.coordinates}
              duration={d.duration}
            />,
          })
        } else if (msg && !tool) {
          // Thought / iteration progress
          if (msg.includes('iteration') || msg.includes('Iteration')) {
            // Skip iteration counters, too noisy
          } else {
            parsed.push({
              key, weight: 'low',
              component: <ThoughtSegment key={key} title="" body={msg} />,
            })
          }
        } else if (tool) {
          // Generic tool call
          parsed.push({
            key, weight: 'low',
            component: <CommandActivityRow key={key}
              command={`${tool}(${truncate(args, 60)})`}
              status="completed"
            />,
          })
        }

        // Track output if present
        if (d.output && (d.type === 'tool_output' || d.type === 'plan_output')) {
          parsed.push({
            key: key + '-out', weight: 'low',
            component: (
              <ThoughtSegment key={key + '-out'}
                title={d.type === 'plan_output' ? 'Agent-core plan' : 'Tool output'}
                body={typeof d.output === 'string' ? d.output.slice(0, 2000) : JSON.stringify(d.output).slice(0, 2000)}
              />
            ),
          })
        }
        break
      }

      case 'action_completed': {
        const elapsed = segmentStart
          ? new Date(ev.timestamp).getTime() - segmentStart
          : 0
        parsed.push({
          key: key + '-seg', weight: 'medium',
          component: <WorkSegmentHeader key={key + '-seg'}
            expanded={segmentExpanded}
            duration={formatDuration(elapsed)}
            additions={segmentAdditions || d.files_edited?.length}
            deletions={segmentDeletions}
            onToggle={() => { segmentExpanded = !segmentExpanded }}
          />,
        })
        parsed.push({
          key, weight: 'high',
          component: <AgentMessage key={key} content={msg || 'Action completed'} timestamp={ev.timestamp} />,
        })
        segmentStart = null
        segmentAdditions = 0
        segmentDeletions = 0
        break
      }

      case 'action_failed':
        parsed.push({
          key, weight: 'high',
          component: <AgentErrorBlock key={key}
            title={msg || 'Action failed'}
            body={d.error || ''}
            recoverable={d.recoverable !== false}
            suggestedAction={d.suggested_action}
          />,
        })
        break

      case 'action_blocked':
        parsed.push({
          key, weight: 'high',
          component: <DecisionPromptCard key={key}
            question={msg || 'Action blocked'}
            status="waiting"
            options={d.options}
          />,
        })
        break

      case 'commit_created':
        parsed.push({
          key, weight: 'high',
          component: <CommitCard key={key}
            hash={d.commit_hash || d.hash || ''}
            message={d.commit_message || msg}
            branch={d.branch}
          />,
        })
        break

      case 'pr_created':
        parsed.push({
          key, weight: 'high',
          component: <PullRequestCard key={key}
            number={d.pr_number || 0}
            title={d.pr_title || msg}
            url={d.pr_url}
            status="open"
          />,
        })
        break

      case 'plan_completed':
        parsed.push({
          key, weight: 'high',
          component: <AgentMessage key={key}
            content={`✓ ${msg || 'Plan completed'}`}
            timestamp={ev.timestamp}
          />,
        })
        break

      case 'credential_request':
        parsed.push({
          key, weight: 'medium',
          component: <CredentialRequestCard key={key}
            secretName={d.secret_name || d.secretName || 'unknown'}
            purpose={d.purpose || msg}
            timeoutSeconds={d.timeout || 600}
            status={d.status || 'waiting'}
          />,
        })
        break

      case 'decision_prompt':
        parsed.push({
          key, weight: 'high',
          component: <DecisionPromptCard key={key}
            question={d.question || msg}
            options={d.options}
            selectedOption={d.selected_option || d.selectedOption}
            status={d.status || 'waiting'}
          />,
        })
        break

      case 'recording_event':
        parsed.push({
          key, weight: 'low',
          component: <RecordingEventRow key={key}
            status={d.status || 'started'}
            duration={d.duration_ms || d.durationMs}
          />,
        })
        break

      case 'branch_pushed':
        parsed.push({
          key, weight: 'medium',
          component: <BranchPushedRow key={key}
            branch={d.branch || ''}
            repo={d.remote_repo || d.remoteRepo || d.repo || ''}
            url={d.url}
          />,
        })
        break

      case 'plan_revision':
        parsed.push({
          key, weight: 'high',
          component: <PlanRevisionCard key={key}
            reason={d.reason || msg}
            triggeredBy={d.triggered_by || d.triggeredBy}
            newSteps={d.new_steps || d.newSteps || []}
          />,
        })
        break

      case 'user_override':
        parsed.push({
          key, weight: 'high',
          component: <UserOverrideCard key={key}
            command={d.command || msg}
            skippedSteps={d.skipped_steps || d.skippedSteps}
            riskFlags={d.risk_flags || d.riskFlags}
          />,
        })
        break

      case 'test_report':
        parsed.push({
          key, weight: 'medium',
          component: <TestReportPreparationBlock key={key}
            title={d.title || msg}
            summary={d.summary}
            status={d.status || 'preparing'}
            artifacts={d.artifacts}
          />,
        })
        break

      case 'ci_status':
        parsed.push({
          key, weight: 'medium',
          component: <CiStatusRow key={key}
            prNumber={d.pr_number || d.prNumber || 0}
            status={d.status || 'unknown'}
            message={d.message || msg}
          />,
        })
        break

      case 'test_mode_entered':
        parsed.push({
          key, weight: 'medium',
          component: <TestModeEventRow key={key}
            goal={d.goal || msg}
          />,
        })
        break

      case 'pr_merged':
        parsed.push({
          key, weight: 'high',
          component: (
            <div key={key}>
              <PullRequestCard
                number={d.pr_number || 0}
                title={d.pr_title || msg}
                url={d.pr_url}
                status="merged"
              />
              {d.review_url && (
                <ReviewActionBar label="Review with Devin" actions={[
                  { label: 'Analyze', kind: 'primary' },
                ]} />
              )}
            </div>
          ),
        })
        break

      case 'git_action': {
        const gitAction = d.action || d.git_action || 'commit'
        if (gitAction === 'push' && d.branch) {
          parsed.push({
            key, weight: 'medium',
            component: <BranchPushedRow key={key}
              branch={d.branch}
              repo={d.repo || d.remote || ''}
              url={d.url}
            />,
          })
        } else {
          parsed.push({
            key, weight: 'medium',
            component: <GitActivityRow key={key}
              action={gitAction}
              commandPreview={d.command_preview || d.commandPreview}
              message={d.message || msg}
              branch={d.branch}
              remote={d.remote || d.repo}
            />,
          })
        }
        break
      }

      case 'secret_provided':
        parsed.push({
          key, weight: 'medium',
          component: <AgentMessage key={key}
            content="Secret received and redacted"
            timestamp={ev.timestamp}
          />,
        })
        break

      case 'awaiting_instructions':
        parsed.push({
          key, weight: 'high',
          component: (
            <div key={key} className="as-awaiting">
              <Circle size={14} className="as-awaiting-icon" />
              <span>Agent is awaiting instructions</span>
            </div>
          ),
        })
        break

      default: {
        // Fallback: render as thought/message
        if (msg) {
          parsed.push({
            key, weight: 'low',
            component: <AgentMessage key={key} content={msg} timestamp={ev.timestamp} />,
          })
        }
        break
      }
    }
  }

  return parsed
}

// ─── floating guide composer ─────────────────────────────────────────────────

function FloatingGuideComposer({
  sessionId, isRunning, onSend, onStop,
}: {
  sessionId: string; isRunning: boolean
  onSend: (instruction: string) => void
  onStop?: () => void
}) {
  const [value, setValue] = useState('')

  const handleSend = () => {
    if (!value.trim()) return
    onSend(value.trim())
    setValue('')
  }

  return (
    <div className="as-composer">
      <button className="as-composer-attach" title="Add context">
        <Plus size={18} />
      </button>
      <input
        className="as-composer-input"
        placeholder={isRunning ? 'Guide agent while it works' : 'Send a message'}
        value={value}
        onChange={e => setValue(e.target.value)}
        onKeyDown={e => e.key === 'Enter' && !e.shiftKey && handleSend()}
      />
      <button className="as-composer-mic" title="Voice input">
        <Mic size={18} />
      </button>
      {isRunning ? (
        <button className="as-composer-stop" title="Stop" onClick={onStop}>
          <Square size={14} fill="white" />
        </button>
      ) : (
        <button className="as-composer-send" title="Send" onClick={handleSend} disabled={!value.trim()}>
          <Send size={16} />
        </button>
      )}
    </div>
  )
}

// ─── main page ───────────────────────────────────────────────────────────────

export default function AgentSessionPage({
  sessionId, model, onBack, sessions: externalSessions, onNavigateSession,
}: {
  sessionId: string; model?: string; onBack?: () => void
  sessions?: SidebarSession[]; onNavigateSession?: (id: string) => void
}) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [events, setEvents] = useState<SessionEvent[]>([])
  const [isRunning, setIsRunning] = useState(false)
  const [liveStatus, setLiveStatus] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)
  const lastSeqRef = useRef(0)
  const pollingRef = useRef(true)

  // Derive session title from first user prompt or session ID
  const sessionTitle = useMemo(() => {
    const firstPrompt = events.find(e => e.event_type === 'user_prompt_received')
    if (firstPrompt) {
      const msg = firstPrompt.data?.message || ''
      return truncate(msg, 60)
    }
    return sessionId
  }, [events, sessionId])

  // Derive repos from events
  const repos = useMemo(() => {
    const found: RepoRef[] = []
    const seen = new Set<string>()
    for (const ev of events) {
      if (ev.data?.repo_path) {
        const name = ev.data.repo_path.split('/').pop() || ''
        const key = `MapleEdge/${name}`
        if (!seen.has(key) && name) {
          found.push({ provider: 'github', owner: 'MapleEdge', repo: name })
          seen.add(key)
        }
      }
    }
    return found
  }, [events])

  // Poll events via SSE-like polling
  useEffect(() => {
    pollingRef.current = true
    lastSeqRef.current = 0

    const poll = async () => {
      while (pollingRef.current) {
        try {
          const res = await fetch(`${CONTROL_API}/sessions/${sessionId}/events/stream?after=${lastSeqRef.current}`)
          const data = await res.json()
          if (data.events && data.events.length > 0) {
            lastSeqRef.current = data.total
            setEvents(prev => {
              const existingIds = new Set(prev.map(e => e.event_id))
              const newEvents = data.events.filter((e: SessionEvent) => !existingIds.has(e.event_id))
              return newEvents.length > 0 ? [...prev, ...newEvents] : prev
            })

            // Determine running state
            const last = data.events[data.events.length - 1]
            const et = last.event_type
            if (et === 'action_completed' || et === 'action_failed' || et === 'plan_completed') {
              setIsRunning(false)
              setLiveStatus('')
            } else if (et === 'action_started' || et === 'action_progress') {
              setIsRunning(true)
              const tool = last.data?.tool
              if (tool) {
                setLiveStatus(`Running: ${tool}`)
              } else if (last.data?.message) {
                setLiveStatus(truncate(last.data.message, 40))
              }
            }
          }
        } catch { /* network error, retry */ }
        await new Promise(r => setTimeout(r, 1000))
      }
    }

    // Initial full fetch
    fetch(`${CONTROL_API}/sessions/${sessionId}/events`)
      .then(r => r.json())
      .then(data => {
        if (data.events) {
          setEvents(data.events)
          lastSeqRef.current = data.total || data.events.length
        }
      })
      .catch(() => {})

    // Start polling
    poll()

    return () => { pollingRef.current = false }
  }, [sessionId])

  // Auto-scroll when near bottom
  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 200
    if (isNearBottom) {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
    }
  }, [events])

  const parsedEvents = useMemo(() => parseSessionEvents(events), [events])

  const handleSend = useCallback(async (instruction: string) => {
    setIsRunning(true)
    setLiveStatus('Sending...')
    try {
      await fetch(`${CONTROL_API}/sessions/${sessionId}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instruction, execution_mode: 'finite' }),
      })
    } catch { /* error will show via events */ }
  }, [sessionId])

  // Fetch sessions for sidebar if not provided externally
  const [localSessions, setLocalSessions] = useState<SidebarSession[]>([])
  useEffect(() => {
    if (!externalSessions) {
      fetch(`${CONTROL_API}/sessions`)
        .then(r => r.json())
        .then(d => setLocalSessions(d.sessions || []))
        .catch(() => {})
    }
  }, [externalSessions])
  const sidebarSessions = externalSessions || localSessions

  const handleNavigateSession = useCallback((id: string) => {
    if (onNavigateSession) {
      onNavigateSession(id)
    } else {
      window.location.hash = `/session/${id}`
    }
  }, [onNavigateSession])

  return (
    <div className="as-page">
      <WorkspaceSidebar
        sessions={sidebarSessions}
        activeSessionId={sessionId}
        workspaceName="MapleEdge"
        onNavigate={handleNavigateSession}
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
      />

      <div className="as-page-main">
      <SessionTopBar title={sessionTitle} model={model || 'deepseek-chat'} />

      <div className="as-body">
        {/* Center transcript pane */}
        <div className="as-center-pane">
          <div className="as-scroll" ref={scrollRef}>
            <div className="as-transcript">
              <div className="as-timeline">
                {parsedEvents.map(pe => (
                  <div key={pe.key} className={`as-timeline-item as-weight-${pe.weight}`}>
                    {pe.component}
                  </div>
                ))}

                {events.length === 0 && (
                  <div className="as-empty">
                    <p>No events yet. Send a message to start working.</p>
                  </div>
                )}
              </div>
            </div>
          </div>

          <LiveAgentStatus status={liveStatus} animated={isRunning} />

          <FloatingGuideComposer
            sessionId={sessionId}
            isRunning={isRunning}
            onSend={handleSend}
          />
        </div>

        {/* Right artifact/workspace pane */}
        <RightPane events={events} sessionId={sessionId} />
      </div>
      </div>{/* end as-page-main */}
    </div>
  )
}
