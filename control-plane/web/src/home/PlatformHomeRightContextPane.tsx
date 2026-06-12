import { useState } from 'react'
import { Activity, FileText, GitBranch, Info, Monitor } from 'lucide-react'
import type { GraphSession } from './types'

type RightPaneTab = 'worklog' | 'changes' | 'desktop'

export default function PlatformHomeRightContextPane({ activeSession }: { activeSession?: GraphSession | null }) {
  const [activeTab, setActiveTab] = useState<RightPaneTab>('worklog')
  const repoAttached = Boolean(activeSession?.metadata?.repo_session_id || activeSession?.metadata?.repo_attached_at_start)

  return (
    <aside className="platform-right-pane" aria-label="Session context">
      <div className="platform-pane-header">
        <span className="platform-pane-title">Context</span>
        <div className="platform-right-tabs">
          <button className={activeTab === 'worklog' ? 'active' : ''} onClick={() => setActiveTab('worklog')}>Worklog</button>
          <button className={activeTab === 'changes' ? 'active' : ''} onClick={() => setActiveTab('changes')}>Changes</button>
          <button className={activeTab === 'desktop' ? 'active' : ''} onClick={() => setActiveTab('desktop')}>Desktop</button>
        </div>
      </div>
      <div className="platform-pane-body">
        {activeTab === 'worklog' && <WorklogContext activeSession={activeSession} repoAttached={repoAttached} />}
        {activeTab === 'changes' && <ChangesContext />}
        {activeTab === 'desktop' && <DesktopContext />}
      </div>
    </aside>
  )
}

function WorklogContext({ activeSession, repoAttached }: { activeSession?: GraphSession | null; repoAttached: boolean }) {
  return (
    <>
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
    </>
  )
}

function ChangesContext() {
  return <section className="platform-context-card"><h3><FileText size={14} /> Changes</h3><p>No changed files are reported yet. This tab mirrors the old right-pane changes surface.</p></section>
}

function DesktopContext() {
  return <section className="platform-context-card"><h3><Monitor size={14} /> Desktop</h3><p>Remote desktop preview belongs here once graph-native execution is connected.</p></section>
}
