import type { GitHubRepo } from './types'
import { getControlPlaneJson } from './platformHomeControlPlaneRequestHelpers'

export async function loadVisibleRemoteRepositoriesForPlatformHome(): Promise<GitHubRepo[]> {
  const data = await getControlPlaneJson<{ ok: boolean; repositories: GitHubRepo[]; error?: { message?: string } }>('/repo-provider/repositories')
  if (!data.ok) throw new Error(data.error?.message || 'No repositories returned.')
  return data.repositories || []
}
