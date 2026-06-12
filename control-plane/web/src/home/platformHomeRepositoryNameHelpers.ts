import type { GitHubRepo } from './types'

export function displayNameForGitHubRepository(repo: GitHubRepo): string {
  return repo.full_name || repo.name || 'GitHub repository'
}

export function displayNameForLocalRepositoryPath(path: string): string {
  return path.split('/').filter(Boolean).at(-1) || path || 'Local folder'
}

export function compactTitleFromInitialPrompt(prompt: string): string {
  const normalized = prompt.replace(/\s+/g, ' ').trim()
  if (!normalized) return 'New session'
  return normalized.length > 82 ? `${normalized.slice(0, 82)}…` : normalized
}

export function currentIsoTimestamp(): string {
  return new Date().toISOString()
}
