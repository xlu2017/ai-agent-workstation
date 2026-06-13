import { useCallback, useMemo, useState } from 'react'
import type { BrowseEntry, GitHubRepo, GraphSession, RepoSource } from './types'
import { getControlPlaneJson } from './platformHomeControlPlaneRequestHelpers'
import PlatformHomeRepositoryScopeSelector from './PlatformHomeRepositoryScopeSelector'
import { attachRepositorySelectionToActiveGraphSession } from './attachRepositorySelectionToActiveGraphSession'

export default function PlatformHomeAttachRepositoryToActiveSessionCard({
  activeSession,
  onSessionUpdated,
}: {
  activeSession: GraphSession
  onSessionUpdated?: (session: GraphSession) => void
}) {
  const [repoSource, setRepoSource] = useState<RepoSource>('none')
  const [githubRepos, setGithubRepos] = useState<GitHubRepo[]>([])
  const [githubRepoName, setGithubRepoName] = useState('')
  const [repoQuery, setRepoQuery] = useState('')
  const [localPath, setLocalPath] = useState('')
  const [browsePath, setBrowsePath] = useState('/opt/workstation/repos')
  const [browseEntries, setBrowseEntries] = useState<BrowseEntry[]>([])
  const [loadingRepos, setLoadingRepos] = useState(false)
  const [loadingBrowse, setLoadingBrowse] = useState(false)
  const [attaching, setAttaching] = useState(false)
  const [error, setError] = useState('')
  const selectedGithubRepo = useMemo(() => githubRepos.find(repo => repo.full_name === githubRepoName), [githubRepos, githubRepoName])

  const loadGithubRepos = useCallback(async () => {
    setLoadingRepos(true)
    setError('')
    try {
      const data = await getControlPlaneJson<{ ok: boolean; repositories: GitHubRepo[]; error?: { message?: string } }>('/repo-provider/repositories')
      if (!data.ok) throw new Error(data.error?.message || 'No repositories returned.')
      setGithubRepos(data.repositories || [])
      setGithubRepoName(current => current || data.repositories?.[0]?.full_name || '')
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoadingRepos(false)
    }
  }, [])

  const browseLocalPath = useCallback(async (path: string) => {
    setLoadingBrowse(true)
    setError('')
    try {
      const query = new URLSearchParams({ path }).toString()
      const data = await getControlPlaneJson<{ path: string; entries: BrowseEntry[]; error?: string }>(`/browse?${query}`)
      if (data.error) throw new Error(data.error)
      setBrowsePath(data.path)
      setBrowseEntries(data.entries || [])
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoadingBrowse(false)
    }
  }, [])

  const attachRepository = useCallback(async () => {
    if (repoSource === 'none' || attaching) return
    setAttaching(true)
    setError('')
    try {
      const nextSession = await attachRepositorySelectionToActiveGraphSession({ activeSession, repoSource, selectedGithubRepo, localPath })
      onSessionUpdated?.(nextSession)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setAttaching(false)
    }
  }, [activeSession, attaching, repoSource, selectedGithubRepo, localPath, onSessionUpdated])

  return (
    <section className="platform-context-card platform-attach-repo-card">
      <h3>Attach repository</h3>
      <p>Attach repo context to this existing session before file edits, tests, runtime work, or PR output.</p>
      <PlatformHomeRepositoryScopeSelector repoSource={repoSource} setRepoSource={setRepoSource} repoQuery={repoQuery} setRepoQuery={setRepoQuery} githubRepoName={githubRepoName} setGithubRepoName={setGithubRepoName} githubRepos={githubRepos} localPath={localPath} setLocalPath={setLocalPath} browsePath={browsePath} browseEntries={browseEntries} loadingRepos={loadingRepos} loadingBrowse={loadingBrowse} onLoadGithubRepos={loadGithubRepos} onBrowseLocalPath={browseLocalPath} />
      <button className="platform-button-primary platform-wide-button" disabled={repoSource === 'none' || attaching} onClick={attachRepository}>{attaching ? 'Attaching…' : 'Attach repository'}</button>
      {error && <p className="platform-danger-text">{error}</p>}
    </section>
  )
}
