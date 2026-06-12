import { useCallback, useEffect, useMemo, useState } from 'react'
import type { GraphSession } from './types'
import { getControlPlaneJson } from './platformHomeControlPlaneRequestHelpers'

export function usePlatformHomeGraphSessionList() {
  const [sessions, setSessions] = useState<GraphSession[]>([])
  const [loadingSessions, setLoadingSessions] = useState(false)
  const [sessionListError, setSessionListError] = useState('')
  const [showArchivedSessions, setShowArchivedSessions] = useState(false)

  const loadSessions = useCallback(async () => {
    setLoadingSessions(true)
    setSessionListError('')
    try {
      const data = await getControlPlaneJson<{ sessions: GraphSession[] }>('/session-graph/sessions')
      setSessions(data.sessions || [])
    } catch (err) {
      setSessionListError((err as Error).message)
    } finally {
      setLoadingSessions(false)
    }
  }, [])

  useEffect(() => { void loadSessions() }, [loadSessions])

  const visibleSessions = useMemo(() => {
    return [...sessions]
      .filter(session => showArchivedSessions || session.status !== 'archived')
      .sort((a, b) => new Date(b.updated_at || b.created_at || 0).getTime() - new Date(a.updated_at || a.created_at || 0).getTime())
  }, [sessions, showArchivedSessions])

  return {
    sessions,
    visibleSessions,
    loadingSessions,
    sessionListError,
    showArchivedSessions,
    setShowArchivedSessions,
    loadSessions,
  }
}
