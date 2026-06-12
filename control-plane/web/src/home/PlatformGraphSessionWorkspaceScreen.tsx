import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ChatTurn, GraphSession } from './types'
import { getControlPlaneJson, patchControlPlaneJson } from './platformHomeControlPlaneRequestHelpers'
import { appendChatTurn, assistantAcknowledgementForPrompt, normalizeChatTurns } from './platformHomeChatTurnHelpers'
import PlatformGraphSessionChatComposer from './PlatformGraphSessionChatComposer'
import PlatformGraphSessionMessageList from './PlatformGraphSessionMessageList'
import PlatformGraphSessionRepoScopeNotice from './PlatformGraphSessionRepoScopeNotice'

export default function PlatformGraphSessionWorkspaceScreen({
  sessionId,
  onNavigate,
}: {
  sessionId: string
  onNavigate: (path: string) => void
}) {
  const [session, setSession] = useState<GraphSession | null>(null)
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
    const userTurns = appendChatTurn(turns, 'user', message)
    const nextTurns: ChatTurn[] = appendChatTurn(
      userTurns,
      'assistant',
      assistantAcknowledgementForPrompt(message, Boolean(session.metadata?.repo_session_id)),
    )
    try {
      const result = await patchControlPlaneJson<{ session: GraphSession }>(`/session-graph/sessions/${session.id}`, {
        state: { ...(session.state || {}), chat_turns: nextTurns },
        metadata: { ...(session.metadata || {}), last_home_chat_at: new Date().toISOString() },
        reason: 'Append home workspace chat turn.',
      })
      setSession(result.session)
      setDraft('')
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }, [draft, session, saving, turns])

  if (error && !session) {
    return <main className="graph-session-page"><section className="graph-session-card"><button className="home-link" onClick={() => onNavigate('/')}>← Home</button><div className="home-error">{error}</div></section></main>
  }

  if (!session) {
    return <main className="graph-session-page"><section className="graph-session-card"><div className="home-kicker">Loading session…</div></section></main>
  }

  return (
    <main className="graph-session-page workspace-shell">
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
        <PlatformGraphSessionMessageList turns={turns} />
        <PlatformGraphSessionChatComposer value={draft} disabled={saving} onChange={setDraft} onSubmit={submitDraft} />
        {error && <div className="home-error">{error}</div>}
      </section>
    </main>
  )
}
