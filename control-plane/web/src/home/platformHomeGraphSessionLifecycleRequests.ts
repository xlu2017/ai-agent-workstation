import type { GraphSession } from './types'
import { patchControlPlaneJson } from './platformHomeControlPlaneRequestHelpers'

export async function archiveGraphSessionFromPlatformHome(session: GraphSession): Promise<GraphSession> {
  const response = await patchControlPlaneJson<{ session: GraphSession }>(`/session-graph/sessions/${session.id}`, {
    status: 'archived',
    metadata: { ...(session.metadata || {}), archived_at: new Date().toISOString() },
    reason: 'Archive session from platform home session log.',
  })
  return response.session
}

export async function restoreGraphSessionFromPlatformHome(session: GraphSession): Promise<GraphSession> {
  const metadata = { ...(session.metadata || {}) }
  delete metadata.archived_at
  delete metadata.deleted_at
  const response = await patchControlPlaneJson<{ session: GraphSession }>(`/session-graph/sessions/${session.id}`, {
    status: 'active',
    metadata,
    merge_metadata: false,
    reason: 'Restore session from platform home session log.',
  })
  return response.session
}

export async function softDeleteGraphSessionFromPlatformHome(session: GraphSession): Promise<GraphSession> {
  const response = await patchControlPlaneJson<{ session: GraphSession }>(`/session-graph/sessions/${session.id}`, {
    status: 'archived',
    metadata: { ...(session.metadata || {}), deleted_at: new Date().toISOString() },
    reason: 'Move session to trash from platform home session log.',
  })
  return response.session
}
