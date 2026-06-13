import { useCallback, useEffect, useState } from 'react'
import type { GraphSessionEvent } from './types'
import { getControlPlaneJson } from './platformHomeControlPlaneRequestHelpers'

export function usePlatformHomeActiveGraphSessionEvents(sessionId?: string, refreshKey?: string) {
  const [events, setEvents] = useState<GraphSessionEvent[]>([])
  const [loadingEvents, setLoadingEvents] = useState(false)
  const [eventError, setEventError] = useState('')

  const loadEvents = useCallback(async () => {
    if (!sessionId) {
      setEvents([])
      return
    }
    setLoadingEvents(true)
    setEventError('')
    try {
      const query = new URLSearchParams({ session_id: sessionId }).toString()
      const data = await getControlPlaneJson<{ events: GraphSessionEvent[] }>(`/session-graph/events?${query}`)
      setEvents(data.events || [])
    } catch (err) {
      setEventError((err as Error).message)
    } finally {
      setLoadingEvents(false)
    }
  }, [sessionId, refreshKey])

  useEffect(() => { void loadEvents() }, [loadEvents])

  return { events, loadingEvents, eventError, loadEvents }
}
