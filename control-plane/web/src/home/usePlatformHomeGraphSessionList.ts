import { useCallback, useEffect, useMemo, useState } from 'react'
import type { GraphSession } from './types'
import { getControlPlaneJson } from './platformHomeControlPlaneRequestHelpers'
import {
  archiveGraphSessionFromPlatformHome,
  restoreGraphSessionFromPlatformHome,
  softDeleteGraphSessionFromPlatformHome,
} from './platformHomeGraphSessionLifecycleRequests'

export type PlatformHomeSessionListFilter = 'active' | 'archived' | 'trash' | 'all'

function isSoftDeletedSession(session: GraphSession): boolean {
  return Boolean(session.metadata?.deleted_at)
}

function matchesFilter(session: GraphSession, filter: PlatformHomeSessionListFilter): boolean {
  if (filter === 'all') return true
  if (filter === 'trash') return isSoftDeletedSession(session)
  if (filter === 'archived') return session.status === 'archived' && !isSoftDeletedSession(session)
  return session.status !== 'archived' && !isSoftDeletedSession(session)
}

export function usePlatformHomeGraphSessionList() {
  const [sessions, setSessions] = useState<GraphSession[]>([])
  const [loadingSessions, setLoadingSessions] = useState(false)
  const [sessionListError, setSessionListError] = useState('')
  const [filter, setFilter] = useState<PlatformHomeSessionListFilter>('active')
  const [searchText, setSearchText] = useState('')

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
    const query = searchText.trim().toLowerCase()
    return [...sessions]
      .filter(session => matchesFilter(session, filter))
      .filter(session => !query || `${session.title} ${session.kind} ${session.status} ${session.summary || ''}`.toLowerCase().includes(query))
      .sort((a, b) => new Date(b.updated_at || b.created_at || 0).getTime() - new Date(a.updated_at || a.created_at || 0).getTime())
  }, [sessions, filter, searchText])

  const replaceSession = useCallback((nextSession: GraphSession) => {
    setSessions(previous => previous.map(session => session.id === nextSession.id ? nextSession : session))
  }, [])

  const archiveSession = useCallback(async (session: GraphSession) => {
    replaceSession(await archiveGraphSessionFromPlatformHome(session))
  }, [replaceSession])

  const restoreSession = useCallback(async (session: GraphSession) => {
    replaceSession(await restoreGraphSessionFromPlatformHome(session))
  }, [replaceSession])

  const softDeleteSession = useCallback(async (session: GraphSession) => {
    replaceSession(await softDeleteGraphSessionFromPlatformHome(session))
  }, [replaceSession])

  return {
    sessions,
    visibleSessions,
    loadingSessions,
    sessionListError,
    filter,
    setFilter,
    searchText,
    setSearchText,
    loadSessions,
    archiveSession,
    restoreSession,
    softDeleteSession,
  }
}
