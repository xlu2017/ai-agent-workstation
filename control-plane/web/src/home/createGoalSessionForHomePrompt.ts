import type { GraphSession } from './types'
import { postControlPlaneJson } from './platformHomeControlPlaneRequestHelpers'
import { compactTitleFromInitialPrompt } from './platformHomeRepositoryNameHelpers'

export async function createGoalSessionForHomePrompt(prompt: string, repoSession: GraphSession | null): Promise<GraphSession> {
  const response = await postControlPlaneJson<{ session: GraphSession }>('/session-graph/sessions', {
    kind: 'goal',
    title: compactTitleFromInitialPrompt(prompt),
    summary: prompt,
    status: 'active',
    facets: { goal: { initial_prompt: prompt, repo_optional_at_start: true } },
    state: { initial_prompt: prompt, chat_turns: [{ role: 'user', content: prompt }] },
    metadata: {
      created_from: 'home_chat',
      repo_attached_at_start: Boolean(repoSession),
      repo_session_id: repoSession?.id || null,
    },
  })
  return response.session
}
