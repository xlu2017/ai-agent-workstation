import { Activity, GitBranch, Info } from 'lucide-react'
import type { GraphSession } from './types'

export default function PlatformHomeRightContextPane({ activeSession }: { activeSession?: GraphSession | null }) {
  const repoAttached = Boolean(activeSession?.metadata?.repo_session_id || activeSession?.metadata?.repo_attached_at_start)
  return (
    <aside className="platform-right-pane" aria-label="Session context">
      <div className="platform-pane-header">
        <span className="platform-pane-title">Context</span>
      </div>
      <div className="platform-pane-body">
        <section className="platform-context-card">
          <h3><Info size={14} /> Active session</h3>
          <p>{activeSession ? activeSession.title : 'No active session selected.'}</p>
          {activeSession && <span className="platform-status-pill">{activeSession.status || 'unknown'}</span>}
        </section>
        <section className="platform-context-card">
          <h3><GitBranch size={14} /> Repository scope</h3>
          <p>{repoAttached ? 'Repo context is mounted for this session.' : 'No repo context is mounted. Select one before file edits or tests.'}</p>
        </section>
        <section className="platform-context-card">
          <h3><Activity size={14} /> Worklog</h3>
          <p>Graph-native execution events will appear here once the execution bridge is wired.</p>
        </section>
      </div>
    </aside>
  )
}
