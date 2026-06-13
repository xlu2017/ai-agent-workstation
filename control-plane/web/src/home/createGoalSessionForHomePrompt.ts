import type { GraphSession, RepoSource } from './types'
import { postControlPlaneJson } from './platformHomeControlPlaneRequestHelpers'
import { compactTitleFromInitialPrompt } from './platformHomeRepositoryNameHelpers'

type HomeGoalSessionOptions = {
  runtime?: string
  repoSource?: RepoSource
}

export async function createGoalSessionForHomePrompt(prompt: string, repoSession: GraphSession | null, options: HomeGoalSessionOptions = {}): Promise<GraphSession> {
  const runtime = options.runtime || 'ubuntu'
  const response = await postControlPlaneJson<{ session: GraphSession }>('/session-graph/sessions', {
    kind: 'goal',
    title: compactTitleFromInitialPrompt(prompt),
    summary: prompt,
    status: 'active',
    facets: {
      goal: { initial_prompt: prompt, repo_optional_at_start: true },
      runtime: { selected_runtime: runtime, selected_repo_source: options.repoSource || 'github' },
    },
    state: { initial_prompt: prompt, chat_turns: [{ role: 'user', content: prompt }], selected_runtime: runtime },
    metadata: {
      created_from: 'home_chat',
      repo_attached_at_start: Boolean(repoSession),
      repo_session_id: repoSession?.id || null,
      selected_runtime: runtime,
      selected_repo_source: options.repoSource || 'github',
    },
  })
  return response.session
}
