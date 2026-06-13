import type { GraphSession } from './types'
import { postControlPlaneJson } from './platformHomeControlPlaneRequestHelpers'

export async function mountRepositorySessionUnderGoalSession({
  repoSession,
  goalSession,
  userIntent,
}: {
  repoSession: GraphSession
  goalSession: GraphSession
  userIntent: string
}): Promise<void> {
  await postControlPlaneJson('/session-graph/actions/apply', {
    action_name: 'session.mount',
    params: {
      source_session_id: repoSession.id,
      target_session_id: goalSession.id,
      user_intent: userIntent,
      mount_mode: 'reference',
      create_adaptation_session: true,
      make_active: true,
    },
  })
}
