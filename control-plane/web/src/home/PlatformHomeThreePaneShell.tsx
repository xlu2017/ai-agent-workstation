import type { ReactNode } from 'react'
import type { GraphSession } from './types'
import { usePlatformHomeGraphSessionList } from './usePlatformHomeGraphSessionList'
import PlatformHomeLeftSessionLogPane from './PlatformHomeLeftSessionLogPane'
import PlatformHomeRightContextPane from './PlatformHomeRightContextPane'

export default function PlatformHomeThreePaneShell({
  activeSession,
  onNavigate,
  children,
}: {
  activeSession?: GraphSession | null
  onNavigate: (path: string) => void
  children: ReactNode
}) {
  const sessionList = usePlatformHomeGraphSessionList()
  const activeSessionId = activeSession?.id

  return (
    <div className="platform-three-pane-shell">
      <PlatformHomeLeftSessionLogPane
        sessions={sessionList.visibleSessions}
        activeSessionId={activeSessionId}
        loading={sessionList.loadingSessions}
        showArchived={sessionList.showArchivedSessions}
        onToggleArchived={() => sessionList.setShowArchivedSessions(!sessionList.showArchivedSessions)}
        onRefresh={sessionList.loadSessions}
        onNewSession={() => onNavigate('/')}
        onSelectSession={sessionId => onNavigate(`/session/${sessionId}`)}
      />
      <main className="platform-center-pane">{children}</main>
      <PlatformHomeRightContextPane activeSession={activeSession} />
    </div>
  )
}
