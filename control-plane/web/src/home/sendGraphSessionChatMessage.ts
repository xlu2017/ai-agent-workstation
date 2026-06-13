import type { GraphSession } from './types'
import { postControlPlaneJson } from './platformHomeControlPlaneRequestHelpers'

export type GraphSessionChatRoute = 'continue_active' | 'question_only' | 'create_child_goal' | 'create_sibling_goal'

export type GraphSessionChatResponse = {
  session: GraphSession
  work_session?: GraphSession
  goal_session?: GraphSession
  chat_status?: 'ready' | 'needs_repo' | GraphSessionChatRoute
  routing_decision?: { route: GraphSessionChatRoute; reason: string }
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
