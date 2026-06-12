import { Folder, Search } from 'lucide-react'
import type { BrowseEntry, GitHubRepo, RepoSource } from './types'
import { displayNameForGitHubRepository } from './platformHomeRepositoryNameHelpers'

export default function PlatformHomeRepositoryScopeSelector(props: {
  repoSource: RepoSource
  setRepoSource: (value: RepoSource) => void
  repoQuery: string
  setRepoQuery: (value: string) => void
  githubRepoName: string
  setGithubRepoName: (value: string) => void
  githubRepos: GitHubRepo[]
  localPath: string
  setLocalPath: (value: string) => void
  browsePath: string
  browseEntries: BrowseEntry[]
  loadingRepos: boolean
  loadingBrowse: boolean
  onLoadGithubRepos: () => void
  onBrowseLocalPath: (path: string) => void
}) {
  return (
    <div className="home-repo-controls">
      <label className="home-field compact">
        <span>Repository scope</span>
        <select value={props.repoSource} onChange={event => props.setRepoSource(event.target.value as RepoSource)}>
          <option value="none">No repo yet</option>
          <option value="github">GitHub repository</option>
          <option value="local">Local repository or folder</option>
        </select>
      </label>

      {props.repoSource === 'github' && <GitHubRepositorySelect {...props} />}
      {props.repoSource === 'local' && <LocalRepositorySelect {...props} />}
    </div>
  )
}

function GitHubRepositorySelect(props: Parameters<typeof PlatformHomeRepositoryScopeSelector>[0]) {
  const query = props.repoQuery.trim().toLowerCase()
  const visibleRepos = query
    ? props.githubRepos.filter(repo => displayNameForGitHubRepository(repo).toLowerCase().includes(query))
    : props.githubRepos

  return (
    <div className="home-field wide">
      <span>GitHub repository</span>
      <div className="home-search-row">
        <Search size={15} />
        <input value={props.repoQuery} onChange={event => props.setRepoQuery(event.target.value)} placeholder="Filter repositories..." />
        <button type="button" onClick={props.onLoadGithubRepos} disabled={props.loadingRepos}>{props.loadingRepos ? 'Loading…' : 'Refresh'}</button>
      </div>
      <select value={props.githubRepoName} onChange={event => props.setGithubRepoName(event.target.value)}>
        <option value="">Select a GitHub repository</option>
        {visibleRepos.map(repo => <option key={repo.full_name || repo.id} value={repo.full_name}>{displayNameForGitHubRepository(repo)}{repo.private ? ' · private' : ''}</option>)}
      </select>
    </div>
  )
}

function LocalRepositorySelect(props: Parameters<typeof PlatformHomeRepositoryScopeSelector>[0]) {
  return (
    <div className="home-field wide">
      <span>Local path</span>
      <div className="home-search-row">
        <Folder size={15} />
        <input value={props.localPath} onChange={event => props.setLocalPath(event.target.value)} placeholder="/opt/workstation/repos/my-repo" />
        <button type="button" onClick={() => props.onBrowseLocalPath(props.localPath || props.browsePath)} disabled={props.loadingBrowse}>{props.loadingBrowse ? 'Loading…' : 'Browse'}</button>
      </div>
      <div className="home-local-browser">
        <div className="home-browser-path">{props.browsePath}</div>
        {props.browseEntries.slice(0, 8).map(entry => (
          <button key={entry.path} type="button" onClick={() => entry.is_repo ? props.setLocalPath(entry.path) : props.onBrowseLocalPath(entry.path)}>
            <Folder size={14} />
            <span>{entry.name}</span>
            {entry.is_repo && <small>repo</small>}
          </button>
        ))}
      </div>
    </div>
  )
}
