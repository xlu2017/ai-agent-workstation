import type { GraphSession } from './types'
import { postControlPlaneJson } from './platformHomeControlPlaneRequestHelpers'

export type GraphSessionChatResponse = {
  session: GraphSession
  work_session?: GraphSession
  chat_status?: 'ready' | 'needs_repo'
}

export async function sendGraphSessionChatMessage({
  sessionId,
  content,
}: {
  sessionId: string
  content: string
}): Promise<GraphSessionChatResponse> {
  return postControlPlaneJson<GraphSessionChatResponse>(`/session-graph/sessions/${sessionId}/chat`, {
    content,
    role: 'user',
    mode: 'finite',
  })
}
