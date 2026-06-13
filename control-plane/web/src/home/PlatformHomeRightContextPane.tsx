import { useState } from 'react'
import { Activity, FileText, GitBranch, Info, Monitor, RefreshCw } from 'lucide-react'
import type { GraphSession, GraphSessionEvent } from './types'
import { usePlatformHomeActiveGraphSessionEvents } from './usePlatformHomeActiveGraphSessionEvents'
import PlatformHomeAttachRepositoryToActiveSessionCard from './PlatformHomeAttachRepositoryToActiveSessionCard'

type RightPaneTab = 'worklog' | 'changes' | 'desktop'

export default function PlatformHomeRightContextPane({
  activeSession,
  onActiveSessionUpdated,
}: {
  activeSession?: GraphSession | null
  onActiveSessionUpdated?: (session: GraphSession) => void
}) {
  const [activeTab, setActiveTab] = useState<RightPaneTab>('worklog')
  const repoAttached = Boolean(activeSession?.metadata?.repo_session_id || activeSession?.metadata?.repo_attached_at_start)
  const eventState = usePlatformHomeActiveGraphSessionEvents(activeSession?.id)

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
        {activeTab === 'worklog' && <WorklogContext activeSession={activeSession} repoAttached={repoAttached} events={eventState.events} loading={eventState.loadingEvents} error={eventState.eventError} onRefresh={eventState.loadEvents} onActiveSessionUpdated={onActiveSessionUpdated} />}
        {activeTab === 'changes' && <ChangesContext events={eventState.events} />}
        {activeTab === 'desktop' && <DesktopContext />}
      </div>
    </aside>
  )
}

function WorklogContext({
  activeSession,
  repoAttached,
  events,
  loading,
  error,
  onRefresh,
  onActiveSessionUpdated,
}: {
  activeSession?: GraphSession | null
  repoAttached: boolean
  events: GraphSessionEvent[]
  loading: boolean
  error: string
  onRefresh: () => void
  onActiveSessionUpdated?: (session: GraphSession) => void
}) {
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
      {activeSession && !repoAttached && <PlatformHomeAttachRepositoryToActiveSessionCard activeSession={activeSession} onSessionUpdated={onActiveSessionUpdated} />}
      <section className="platform-context-card">
        <h3><Activity size={14} /> Worklog <button className="platform-context-icon-button" onClick={onRefresh} title="Refresh events"><RefreshCw size={12} /></button></h3>
        {error && <p className="platform-danger-text">{error}</p>}
        {loading && <p>Loading graph events…</p>}
        {!loading && !events.length && <p>No graph events recorded for this session yet.</p>}
        <div className="platform-event-list">
          {events.slice(-12).reverse().map(event => <GraphEventRow key={event.id} event={event} />)}
        </div>
      </section>
    </>
  )
}

function GraphEventRow({ event }: { event: GraphSessionEvent }) {
  const summary = event.data?.reason || event.data?.source || event.data?.operation || event.actor || ''
  return (
    <div className="platform-event-row">
      <strong>{event.type}</strong>
      <span>{String(summary || 'graph event')}</span>
    </div>
  )
}

function ChangesContext({ events }: { events: GraphSessionEvent[] }) {
  const changeEvents = events.filter(event => event.type.includes('artifact') || event.type.includes('validation') || event.type.includes('action'))
  return (
    <section className="platform-context-card">
      <h3><FileText size={14} /> Changes</h3>
      {!changeEvents.length && <p>No changed files are reported yet. This tab mirrors the old right-pane changes surface.</p>}
      <div className="platform-event-list">
        {changeEvents.slice(-10).reverse().map(event => <GraphEventRow key={event.id} event={event} />)}
      </div>
    </section>
  )
}

function DesktopContext() {
  return <section className="platform-context-card"><h3><Monitor size={14} /> Desktop</h3><p>Remote desktop preview belongs here once graph-native execution is connected.</p></section>
}
