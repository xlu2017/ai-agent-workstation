import type { GraphSession } from './types'
import { postControlPlaneJson } from './platformHomeControlPlaneRequestHelpers'

export async function sendGraphSessionChatMessage({
  sessionId,
  content,
}: {
  sessionId: string
  content: string
}): Promise<GraphSession> {
  const response = await postControlPlaneJson<{ session: GraphSession }>(`/session-graph/sessions/${sessionId}/chat`, {
    content,
    role: 'user',
    execution_mode: localStorage.getItem('settings.defaultExecutionMode') || 'finite',
  })
  return response.session
}
