import type { GitHubRepo, GraphSession, RepoSource } from './types'
import { postControlPlaneJson } from './platformHomeControlPlaneRequestHelpers'
import { displayNameForGitHubRepository, displayNameForLocalRepositoryPath } from './platformHomeRepositoryNameHelpers'

export async function createOptionalRepositorySessionFromHomeSelection({
  repoSource,
  selectedGithubRepo,
  localPath,
}: {
  repoSource: RepoSource
  selectedGithubRepo?: GitHubRepo
  localPath?: string
}): Promise<GraphSession | null> {
  if (repoSource === 'github' && selectedGithubRepo) {
    const response = await postControlPlaneJson<{ session: GraphSession }>('/session-graph/sessions', {
      kind: 'repo',
      title: displayNameForGitHubRepository(selectedGithubRepo),
      summary: selectedGithubRepo.description || `GitHub repository ${displayNameForGitHubRepository(selectedGithubRepo)}`,
      status: 'active',
      facets: {
        repo: {
          source: 'github',
          full_name: selectedGithubRepo.full_name,
          clone_url: selectedGithubRepo.clone_url,
          ssh_url: selectedGithubRepo.ssh_url,
          html_url: selectedGithubRepo.html_url,
          default_branch: selectedGithubRepo.default_branch,
        },
      },
      metadata: { created_from: 'home_chat', repo_source: 'github' },
    })
    return response.session
  }

  if (repoSource === 'local' && localPath?.trim()) {
    const path = localPath.trim()
    const response = await postControlPlaneJson<{ session: GraphSession }>('/session-graph/sessions', {
      kind: 'repo',
      title: displayNameForLocalRepositoryPath(path),
      summary: `Local repository or folder at ${path}`,
      status: 'active',
      facets: { repo: { source: 'local', path, selected_from_home: true } },
      metadata: { created_from: 'home_chat', repo_source: 'local' },
    })
    return response.session
  }

  return null
}
