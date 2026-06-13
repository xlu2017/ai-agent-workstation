import type { GitHubRepo, GraphSession, RepoSource } from './types'
import { patchControlPlaneJson } from './platformHomeControlPlaneRequestHelpers'
import { createOptionalRepositorySessionFromHomeSelection } from './createOptionalRepositorySessionFromHomeSelection'
import { mountRepositorySessionUnderGoalSession } from './mountRepositorySessionUnderGoalSession'

export async function attachRepositorySelectionToActiveGraphSession({
  activeSession,
  repoSource,
  selectedGithubRepo,
  localPath,
}: {
  activeSession: GraphSession
  repoSource: RepoSource
  selectedGithubRepo?: GitHubRepo
  localPath?: string
}): Promise<GraphSession> {
  const repoSession = await createOptionalRepositorySessionFromHomeSelection({ repoSource, selectedGithubRepo, localPath })
  if (!repoSession) return activeSession

  await mountRepositorySessionUnderGoalSession({
    repoSession,
    goalSession: activeSession,
    userIntent: `Attach ${repoSession.title} as context for ${activeSession.title}`,
  })

  const response = await patchControlPlaneJson<{ session: GraphSession }>(`/session-graph/sessions/${activeSession.id}`, {
    metadata: {
      ...(activeSession.metadata || {}),
      repo_attached_at_start: true,
      repo_session_id: repoSession.id,
      repo_attached_from_workspace_at: new Date().toISOString(),
    },
    reason: 'Record repository attachment from graph session workspace.',
  })
  return response.session
}
