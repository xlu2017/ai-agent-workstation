import { useCallback, useEffect, useMemo, useState } from 'react'
import type { GraphSession } from './types'
import { getControlPlaneJson } from './platformHomeControlPlaneRequestHelpers'
import { normalizeChatTurns } from './platformHomeChatTurnHelpers'
import { sendGraphSessionChatMessage } from './sendGraphSessionChatMessage'
import PlatformGraphSessionChatComposer from './PlatformGraphSessionChatComposer'
import PlatformGraphSessionMessageList from './PlatformGraphSessionMessageList'
import PlatformGraphSessionRepoScopeNotice from './PlatformGraphSessionRepoScopeNotice'
import PlatformHomeThreePaneShell from './PlatformHomeThreePaneShell'

export default function PlatformGraphSessionWorkspaceScreen({
  sessionId,
  onNavigate,
}: {
  sessionId: string
  onNavigate: (path: string) => void
}) {
  const [session, setSession] = useState<GraphSession | null>(null)
  const [latestWorkSession, setLatestWorkSession] = useState<GraphSession | null>(null)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const loadSession = useCallback(() => {
    getControlPlaneJson<{ session: GraphSession }>(`/session-graph/sessions/${encodeURIComponent(sessionId)}`)
      .then(data => setSession(data.session))
      .catch(err => setError((err as Error).message))
  }, [sessionId])

  useEffect(() => { loadSession() }, [loadSession])

  const turns = useMemo(() => normalizeChatTurns(session?.state?.chat_turns), [session])

  const submitDraft = useCallback(async () => {
    const message = draft.trim()
    if (!session || !message || saving) return
    setSaving(true)
    setError('')
    try {
      const response = await sendGraphSessionChatMessage({ sessionId: session.id, content: message })
      setSession(response.session)
      setLatestWorkSession(response.work_session || null)
      setDraft('')
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }, [draft, session, saving])

  if (error && !session) {
    return (
      <PlatformHomeThreePaneShell activeSession={null} onNavigate={onNavigate}>
        <section className="graph-session-card"><button className="home-link" onClick={() => onNavigate('/')}>← Home</button><div className="home-error">{error}</div></section>
      </PlatformHomeThreePaneShell>
    )
  }

  if (!session) {
    return (
      <PlatformHomeThreePaneShell activeSession={null} onNavigate={onNavigate}>
        <section className="graph-session-card"><div className="home-kicker">Loading session…</div></section>
      </PlatformHomeThreePaneShell>
    )
  }

  return (
    <PlatformHomeThreePaneShell activeSession={session} onActiveSessionUpdated={setSession} onNavigate={onNavigate}>
      <div className="graph-session-page workspace-shell">
        <header className="graph-session-header">
          <button className="home-link" onClick={() => onNavigate('/')}>← New session</button>
          <button className="home-link" onClick={() => onNavigate('/session-graph')}>Open graph</button>
        </header>
        <section className="workspace-main-card">
          <div className="workspace-title-row">
            <div>
              <div className="home-kicker">Graph session workspace</div>
              <h1>{session.title}</h1>
            </div>
            <span className="workspace-kind-pill">{session.kind}</span>
          </div>
          <PlatformGraphSessionRepoScopeNotice session={session} />
          {latestWorkSession && <div className="workspace-work-created">Created work session: <strong>{latestWorkSession.title}</strong></div>}
          <PlatformGraphSessionMessageList turns={turns} />
          <PlatformGraphSessionChatComposer value={draft} disabled={saving} onChange={setDraft} onSubmit={submitDraft} />
          {error && <div className="home-error">{error}</div>}
        </section>
      </div>
    </PlatformHomeThreePaneShell>
  )
}
