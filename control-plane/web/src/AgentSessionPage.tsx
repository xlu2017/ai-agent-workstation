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
  closeable?: boolean
}

// ─── timeline data model ──────────────────────────────────────────────────

interface SessionTimelinePoint {
  id: string
  sessionId: string
  timestamp: string
  offsetMs: number
  kind: 'prompt' | 'action' | 'desktop_state' | 'desktop_snapshot' | 'worklog' | 'change' | 'pr' | 'error' | 'status'
  title: string
  summary?: string
  url?: string
  prompt?: string
  desktopActive: boolean
  hasDesktopSnapshot?: boolean
  worklogEventId?: string
  changeWindowId?: string
  artifactTab?: 'desktop' | 'worklog' | 'changes' | 'pr' | 'file'
  metadata?: Record<string, unknown>
}

interface SessionTimelineSegment {
  id: string
  startOffsetMs: number
  endOffsetMs: number
  desktopActive: boolean
  eventCount: number
}

const SECRET_PATTERNS = [
  /\b(ghp_[A-Za-z0-9]{36,})\b/,
  /\b(gho_[A-Za-z0-9]{36,})\b/,
  /\b(glpat-[A-Za-z0-9-]{20,})\b/,
  /\b(sk-[A-Za-z0-9]{20,})\b/,
  /\bBearer\s+[A-Za-z0-9._-]{20,}/i,
  /\b(AKIA[A-Z0-9]{16})\b/,
  /tskey-[A-Za-z0-9-]+/,
  /-----BEGIN\s+\w+\s+PRIVATE\s+KEY-----/,
  /password\s*[:=]\s*\S+/i,
]

function redactSecrets(text: string): string {
  let result = text
  for (const pat of SECRET_PATTERNS) {
    result = result.replace(new RegExp(pat.source, 'gi'), '[redacted]')
  }
  return result
}

function buildTimelineFromEvents(events: SessionEvent[], sessionId: string): { points: SessionTimelinePoint[]; segments: SessionTimelineSegment[] } {
  const points: SessionTimelinePoint[] = []
  const startTime = events.length > 0 ? new Date(events[0].timestamp).getTime() : Date.now()
  let desktopActive = false

  for (const ev of events) {
    const ts = new Date(ev.timestamp).getTime()
    const offsetMs = ts - startTime
    const d = ev.data || {}
    let kind: SessionTimelinePoint['kind'] = 'status'
    let title = ev.event_type.replace(/_/g, ' ')
    let prompt: string | undefined
    let url: string | undefined
    let artifactTab: SessionTimelinePoint['artifactTab']

    switch (ev.event_type) {
      case 'user_prompt_received':
        kind = 'prompt'; title = d.message || 'User prompt'; prompt = d.message; break
      case 'action_started': case 'action_progress': case 'action_completed':
        kind = 'action'; title = d.tool ? `${d.tool}` : title
        if (d.tool === 'browser_action') { url = d.url; desktopActive = true }
        break
      case 'action_failed': case 'plan_validation_failed':
        kind = 'error'; title = d.message || 'Error'; break
      case 'pr_created': case 'pr_merged':
        kind = 'pr'; title = `PR #${d.pr_number || ''}`; artifactTab = 'pr'; break
      case 'commit_created': case 'branch_pushed': case 'git_action':
        kind = 'change'; artifactTab = 'changes'; break
      default:
        break
    }

    points.push({
      id: ev.event_id || `tp-${points.length}`,
      sessionId,
      timestamp: ev.timestamp,
      offsetMs,
      kind,
      title: redactSecrets(title),
      summary: d.args_summary ? redactSecrets(truncate(d.args_summary, 100)) : undefined,
      url,
      prompt: prompt ? redactSecrets(truncate(prompt, 120)) : undefined,
      desktopActive,
      artifactTab,
      metadata: { event_type: ev.event_type },
    })
  }

  // Build segments
  const segments: SessionTimelineSegment[] = []
  const totalDuration = points.length > 0 ? points[points.length - 1].offsetMs : 1
  const segCount = Math.min(40, Math.max(5, Math.ceil(points.length / 3)))
  const segDuration = totalDuration / segCount || 1

  for (let i = 0; i < segCount; i++) {
    const segStart = i * segDuration
    const segEnd = (i + 1) * segDuration
    const segPoints = points.filter(p => p.offsetMs >= segStart && p.offsetMs < segEnd)
    const hasDesktop = segPoints.some(p => p.desktopActive)
    segments.push({
      id: `seg-${i}`,
      startOffsetMs: segStart,
      endOffsetMs: segEnd,
      desktopActive: hasDesktop,
      eventCount: segPoints.length,
    })
  }

  return { points, segments }
}

/* Artifact tab strip — closeable tabs */
function ArtifactTabStrip({ tabs, activeIndex, onSelect, onClose }: {
  tabs: ArtifactTab[]; activeIndex: number; onSelect: (i: number) => void; onClose?: (i: number) => void
}) {
  return (
    <div className="as-tab-strip">
      {tabs.map((tab, i) => (
        <div
          key={i}
          className={`as-tab ${i === activeIndex ? 'as-tab-active' : ''}`}
          onClick={() => onSelect(i)}
          role="tab"
          aria-selected={i === activeIndex}
          aria-label={tab.label}
        >
          {tab.kind === 'pr' && <GitPullRequest size={12} />}
          {tab.kind === 'desktop' && <Monitor size={12} />}
          {tab.kind === 'file' && <File size={12} />}
          {tab.kind === 'recording' && <Video size={12} />}
          {tab.kind === 'worklog' && <Hash size={12} />}
          {tab.kind === 'changes' && <FileText size={12} />}
          <span>{tab.label}</span>
          {tab.closeable !== false && onClose && (
            <button
              className="as-tab-close"
              onClick={e => { e.stopPropagation(); onClose(i) }}
              aria-label={`Close ${tab.label}`}
              title={`Close ${tab.label}`}
            >
              <X size={10} />
            </button>
          )}
        </div>
      ))}
      <button className="as-tab as-tab-add" title="Add tab" aria-label="Add tab">
        <Plus size={12} />
      </button>
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

/* Timeline scrubber — full replay bar */
function TimelineScrubber({
  points, segments, selectedPointId, followLive,
  onSelectPoint, onPrev, onNext, onGoLive, onGoEnd,
}: {
  points: SessionTimelinePoint[]; segments: SessionTimelineSegment[]
  selectedPointId?: string; followLive: boolean
  onSelectPoint: (point: SessionTimelinePoint) => void
  onPrev: () => void; onNext: () => void
  onGoLive: () => void; onGoEnd: () => void
}) {
  const [hoverPoint, setHoverPoint] = useState<SessionTimelinePoint | null>(null)
  const [hoverX, setHoverX] = useState(0)
  const trackRef = useRef<HTMLDivElement>(null)
  const totalDuration = segments.length > 0 ? segments[segments.length - 1].endOffsetMs : 1

  const handleTrackClick = useCallback((e: React.MouseEvent) => {
    if (!trackRef.current || points.length === 0) return
    const rect = trackRef.current.getBoundingClientRect()
    const pct = (e.clientX - rect.left) / rect.width
    const targetOffset = pct * totalDuration
    let nearest = points[0]
    let bestDist = Math.abs(nearest.offsetMs - targetOffset)
    for (const p of points) {
      const dist = Math.abs(p.offsetMs - targetOffset)
      if (dist < bestDist) { nearest = p; bestDist = dist }
    }
    onSelectPoint(nearest)
  }, [points, totalDuration, onSelectPoint])

  const handleTrackHover = useCallback((e: React.MouseEvent) => {
    if (!trackRef.current || points.length === 0) return
    const rect = trackRef.current.getBoundingClientRect()
    const pct = (e.clientX - rect.left) / rect.width
    setHoverX(e.clientX - rect.left)
    const targetOffset = pct * totalDuration
    let nearest = points[0]
    let bestDist = Math.abs(nearest.offsetMs - targetOffset)
    for (const p of points) {
      const dist = Math.abs(p.offsetMs - targetOffset)
      if (dist < bestDist) { nearest = p; bestDist = dist }
    }
    setHoverPoint(nearest)
  }, [points, totalDuration])

  return (
    <div className="as-scrubber">
      <button className="as-scrubber-btn" title="Previous event" aria-label="Previous event" onClick={onPrev}>
        <ArrowLeft size={14} />
      </button>

      <div className="as-scrubber-track" ref={trackRef}
        onClick={handleTrackClick}
        onMouseMove={handleTrackHover}
        onMouseLeave={() => setHoverPoint(null)}
      >
        {/* Segments */}
        {segments.map(seg => {
          const widthPct = ((seg.endOffsetMs - seg.startOffsetMs) / totalDuration) * 100
          return (
            <div
              key={seg.id}
              className={`as-scrubber-seg ${seg.desktopActive ? 'as-seg-active' : 'as-seg-inactive'}`}
              style={{ width: `${widthPct}%` }}
            />
          )
        })}

        {/* Event markers */}
        {points.filter(p => p.kind === 'prompt' || p.kind === 'action' || p.kind === 'error' || p.kind === 'pr').map(p => {
          const leftPct = (p.offsetMs / totalDuration) * 100
          const isSelected = p.id === selectedPointId
          return (
            <div
              key={p.id}
              className={`as-scrubber-marker ${isSelected ? 'as-marker-selected' : ''} as-marker-${p.kind}`}
              style={{ left: `${leftPct}%` }}
            />
          )
        })}

        {/* Hover tooltip */}
        {hoverPoint && (
          <div className="as-scrubber-tooltip" style={{ left: hoverX }}>
            <div className="as-tooltip-time">{new Date(hoverPoint.timestamp).toLocaleString()}</div>
            <div className="as-tooltip-title">
              {hoverPoint.kind === 'prompt' && hoverPoint.prompt
                ? `Prompt: "${hoverPoint.prompt}"`
                : hoverPoint.url || hoverPoint.title}
            </div>
            {hoverPoint.summary && <div className="as-tooltip-summary">{hoverPoint.summary}</div>}
          </div>
        )}
      </div>

      <button className="as-scrubber-btn" title="Next event" aria-label="Next event" onClick={onNext}>
        <ArrowRight size={14} />
      </button>

      {followLive ? (
        <button className="as-scrubber-live" title="Live" aria-label="Live" onClick={onGoLive}>
          <span className="as-live-pip" /> Live
        </button>
      ) : (
        <button className="as-scrubber-btn as-scrubber-golive" title="Go to live desktop" aria-label="Go to live desktop" onClick={onGoLive}>
          <Monitor size={14} /> Live
        </button>
      )}

      <button className="as-scrubber-btn" title="Go to end" aria-label="Go to end" onClick={onGoEnd}>
        <SkipForward size={14} />
      </button>
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

/* Guacamole Desktop view */
function GuacamoleDesktopView({ followLive, selectedTime }: {
  followLive: boolean; selectedTime?: string
}) {
  const [frameSrc, setFrameSrc] = useState('')
  const [status, setStatus] = useState<'loading' | 'live' | 'unavailable' | 'historical'>('loading')
  const [error, setError] = useState('')

  useEffect(() => {
    if (!followLive && selectedTime) {
      setStatus('historical')
      return
    }
    // Try to get Guacamole config and create session
    fetch(`${CONTROL_API}/v2/remote-desktop/config`)
      .then(r => r.json())
      .then(config => {
        if (!config.enabled) { setStatus('unavailable'); setError('Remote desktop is not enabled'); return }
        if (config.auto_login) {
          fetch(`${CONTROL_API}/v2/remote-desktop/token`, { method: 'POST' })
            .then(async r => { if (!r.ok) throw new Error(await r.text()); return r.json() })
            .then(session => {
              localStorage.setItem('GUAC_AUTH', JSON.stringify({
                authToken: session.authToken, username: session.username,
                dataSource: session.dataSource, availableDataSources: session.availableDataSources,
              }))
              setFrameSrc(session.connection_url || config.url)
              setStatus('live')
            })
            .catch(() => { setFrameSrc(config.url); setStatus('live') })
        } else {
          setFrameSrc(config.url)
          setStatus('live')
        }
      })
      .catch(() => { setStatus('unavailable'); setError('Unable to connect to remote desktop') })
  }, [followLive, selectedTime])

  if (status === 'loading') {
    return (
      <div className="as-desktop-view as-desktop-loading">
        <Loader size={24} className="as-spin" />
        <p>Connecting to remote desktop...</p>
      </div>
    )
  }

  if (status === 'historical') {
    return (
      <div className="as-desktop-view as-desktop-historical">
        <Monitor size={48} className="as-desktop-icon-muted" />
        <p>No desktop snapshot is available for this time.</p>
        {selectedTime && <span className="as-desktop-time">{new Date(selectedTime).toLocaleString()}</span>}
      </div>
    )
  }

  if (status === 'unavailable') {
    return (
      <div className="as-desktop-view as-desktop-unavailable">
        <Monitor size={48} className="as-desktop-icon-muted" />
        <p>{error || 'Desktop is not available'}</p>
        <button className="as-action-btn" onClick={() => {
          if (typeof window !== 'undefined') window.open('/remote-desktop', '_blank')
        }}>
          <ExternalLink size={14} /> <span>Open Desktop</span>
        </button>
      </div>
    )
  }

  return (
    <div className="as-desktop-view as-desktop-live">
      {frameSrc ? (
        <iframe
          title="Remote Desktop"
          src={frameSrc}
          className="as-desktop-iframe"
          allow="fullscreen; clipboard-read; clipboard-write"
          allowFullScreen
        />
      ) : (
        <div className="as-desktop-loading">
          <Loader size={24} className="as-spin" />
          <p>Opening remote desktop...</p>
        </div>
      )}
    </div>
  )
}

/* Resizable two-pane body: center (children) + right pane with drag divider */
function ResizableBody({ events, sessionId, children }: {
  events: SessionEvent[]; sessionId: string; children: React.ReactNode
}) {
  const [rightWidth, setRightWidth] = useState(420)
  const dragging = useRef(false)

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    dragging.current = true
    const startX = e.clientX
    const startW = rightWidth

    const onMove = (ev: MouseEvent) => {
      if (!dragging.current) return
      const delta = startX - ev.clientX
      const newW = Math.max(120, startW + delta)
      setRightWidth(newW)
    }
    const onUp = () => {
      dragging.current = false
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [rightWidth])

  return (
    <div className="as-body">
      {children}
      <div
        className="as-resize-divider"
        onMouseDown={onMouseDown}
        title="Drag to resize"
      />
      <RightPane events={events} sessionId={sessionId} style={{ width: rightWidth }} />
    </div>
  )
}

/* Right pane — artifact inspector with full timeline replay */
function RightPane({ events, sessionId, style }: { events: SessionEvent[]; sessionId: string; style?: React.CSSProperties }) {
  const [activeTab, setActiveTab] = useState(0)
  const [collapsed, setCollapsed] = useState(false)

  // Timeline replay state
  const [selectedPointId, setSelectedPointId] = useState<string | undefined>(undefined)
  const [selectedTime, setSelectedTime] = useState<string | undefined>(undefined)
  const [followLive, setFollowLive] = useState(true)

  // Build tabs from events
  const [closedTabs, setClosedTabs] = useState<Set<string>>(new Set())
  const allTabs = useMemo(() => {
    const t: ArtifactTab[] = [
      { kind: 'worklog', label: 'Worklog', closeable: true },
      { kind: 'changes', label: 'Changes', closeable: true },
    ]
    const prNums = new Set<number>()
    const files = new Set<string>()
    for (const ev of events) {
      if (ev.event_type === 'pr_created' && ev.data?.pr_number) {
        const n = ev.data.pr_number
        if (!prNums.has(n)) {
          prNums.add(n)
          t.push({ kind: 'pr', label: `PR #${n}`, prNumber: n, closeable: true })
        }
      }
      if (ev.event_type === 'action_progress' && ev.data?.path) {
        const fp = ev.data.path
        if (!files.has(fp)) {
          files.add(fp)
          if (files.size <= 3) {
            t.push({ kind: 'file', label: fp.split('/').pop() || fp, filePath: fp, closeable: true })
          }
        }
      }
    }
    t.push({ kind: 'desktop', label: 'Desktop', closeable: true })
    return t
  }, [events])

  const tabs = useMemo(() => allTabs.filter((_, i) => !closedTabs.has(String(i))), [allTabs, closedTabs])

  const handleCloseTab = useCallback((visibleIndex: number) => {
    // Map visible index back to allTabs index
    let count = -1
    for (let i = 0; i < allTabs.length; i++) {
      if (!closedTabs.has(String(i))) count++
      if (count === visibleIndex) {
        setClosedTabs(prev => new Set(prev).add(String(i)))
        if (visibleIndex <= activeTab && activeTab > 0) setActiveTab(activeTab - 1)
        return
      }
    }
  }, [allTabs, closedTabs, activeTab])

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

  // Build timeline data
  const { points, segments } = useMemo(() => buildTimelineFromEvents(events, sessionId), [events, sessionId])

  // Timeline navigation
  const selectedIndex = useMemo(() => {
    if (!selectedPointId) return -1
    return points.findIndex(p => p.id === selectedPointId)
  }, [points, selectedPointId])

  const handleSelectPoint = useCallback((point: SessionTimelinePoint) => {
    setSelectedPointId(point.id)
    setSelectedTime(point.timestamp)
    setFollowLive(false)
  }, [])

  const handlePrev = useCallback(() => {
    if (points.length === 0) return
    const significantPoints = points.filter(p => p.kind === 'prompt' || p.kind === 'action' || p.kind === 'error' || p.kind === 'pr')
    if (significantPoints.length === 0) return
    const currentIdx = selectedIndex >= 0
      ? significantPoints.findIndex(p => p.offsetMs < points[selectedIndex].offsetMs)
      : significantPoints.length - 1
    const prevPoints = significantPoints.filter(p =>
      selectedIndex >= 0 ? p.offsetMs < points[selectedIndex].offsetMs : true
    )
    if (prevPoints.length > 0) {
      const prev = prevPoints[prevPoints.length - 1]
      handleSelectPoint(prev)
    }
  }, [points, selectedIndex, handleSelectPoint])

  const handleNext = useCallback(() => {
    if (points.length === 0) return
    const significantPoints = points.filter(p => p.kind === 'prompt' || p.kind === 'action' || p.kind === 'error' || p.kind === 'pr')
    const nextPoints = selectedIndex >= 0
      ? significantPoints.filter(p => p.offsetMs > points[selectedIndex].offsetMs)
      : significantPoints
    if (nextPoints.length > 0) {
      handleSelectPoint(nextPoints[0])
    } else {
      // At the end, go live
      setFollowLive(true)
      setSelectedPointId(undefined)
      setSelectedTime(undefined)
    }
  }, [points, selectedIndex, handleSelectPoint])

  const handleGoLive = useCallback(() => {
    setFollowLive(true)
    setSelectedPointId(undefined)
    setSelectedTime(undefined)
  }, [])

  const handleGoEnd = useCallback(() => {
    if (points.length > 0) {
      const last = points[points.length - 1]
      handleSelectPoint(last)
    }
  }, [points, handleSelectPoint])

  // Changes time filter based on selected time
  const changesTimeFilter = useMemo(() => {
    if (followLive || !selectedTime) return undefined
    return { startTime: events[0]?.timestamp || '', endTime: selectedTime }
  }, [followLive, selectedTime, events])

  if (collapsed) {
    return (
      <div className="as-right-collapsed">
        <button className="as-right-expand" onClick={() => setCollapsed(false)} title="Expand panel" aria-label="Expand panel">
          <ChevronLeft size={16} />
        </button>
      </div>
    )
  }

  return (
    <div className="as-right-pane" style={style}>
      <div className="as-right-header">
        <ArtifactTabStrip tabs={tabs} activeIndex={activeTab} onSelect={setActiveTab} onClose={handleCloseTab} />
        <div className="as-right-header-actions">
          <button className="as-right-expand-btn" title="Expand" aria-label="Expand"><ExternalLink size={14} /></button>
          <button className="as-right-collapse" onClick={() => setCollapsed(true)} title="Collapse" aria-label="Collapse">
            <ChevronRight size={14} />
          </button>
        </div>
      </div>

      <div className="as-right-content">
        {tabs[activeTab]?.kind === 'worklog' && (
          <>
            {!followLive && selectedTime && (
              <div className="as-time-filter">
                <span>Showing worklog at {new Date(selectedTime).toLocaleTimeString()}</span>
                <button className="as-time-filter-clear" onClick={handleGoLive}>Clear</button>
              </div>
            )}
            <WorklogPanel events={events} />
          </>
        )}
        {tabs[activeTab]?.kind === 'changes' && (
          <ChangesPanel files={fileChanges} timeFilter={changesTimeFilter} onClearFilter={handleGoLive} />
        )}
        {tabs[activeTab]?.kind === 'desktop' && (
          <GuacamoleDesktopView followLive={followLive} selectedTime={selectedTime} />
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

      <TimelineScrubber
        points={points}
        segments={segments}
        selectedPointId={selectedPointId}
        followLive={followLive}
        onSelectPoint={handleSelectPoint}
        onPrev={handlePrev}
        onNext={handleNext}
        onGoLive={handleGoLive}
        onGoEnd={handleGoEnd}
      />
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
  sessionId, model, onBack,
}: {
  sessionId: string; model?: string; onBack?: () => void
}) {
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
    // Clear stale data from previous session
    setEvents([])
    setIsRunning(false)
    setLiveStatus('')
    pollingRef.current = true
    lastSeqRef.current = 0
    let cancelled = false

    const poll = async () => {
      while (pollingRef.current && !cancelled) {
        try {
          const res = await fetch(`${CONTROL_API}/sessions/${sessionId}/events/stream?after=${lastSeqRef.current}`)
          if (cancelled) return
          const data = await res.json()
          if (cancelled) return
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
        if (cancelled) return
        if (data.events) {
          setEvents(data.events)
          lastSeqRef.current = data.total || data.events.length
        }
      })
      .catch(() => {})

    // Start polling
    poll()

    return () => {
      pollingRef.current = false
      cancelled = true
    }
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

  const handleStop = useCallback(async () => {
    setLiveStatus('Stopping...')
    try {
      await fetch(`${CONTROL_API}/sessions/${sessionId}/interrupt`, { method: 'POST' })
    } catch { /* */ }
    setIsRunning(false)
    setLiveStatus('Stopped')
  }, [sessionId])

  return (
    <div className="as-page">
      <SessionTopBar title={sessionTitle} model={model || 'deepseek-chat'} />

      <ResizableBody events={events} sessionId={sessionId}>
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
            onStop={handleStop}
          />
        </div>
      </ResizableBody>
    </div>
  )
}
