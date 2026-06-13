import { useCallback, useEffect, useMemo, useState } from 'react'
import { ArrowUp, Loader2 } from 'lucide-react'
import type { BrowseEntry, GitHubRepo, RepoSource } from './types'
import { getControlPlaneJson } from './platformHomeControlPlaneRequestHelpers'
import PlatformHomeRepositoryScopeSelector from './PlatformHomeRepositoryScopeSelector'
import PlatformHomeThreePaneShell from './PlatformHomeThreePaneShell'
import { createOptionalRepositorySessionFromHomeSelection } from './createOptionalRepositorySessionFromHomeSelection'
import { createGoalSessionForHomePrompt } from './createGoalSessionForHomePrompt'
import { mountRepositorySessionUnderGoalSession } from './mountRepositorySessionUnderGoalSession'

export default function PlatformHomeInitialChatScreen({ onNavigate }: { onNavigate: (path: string) => void }) {
  const [prompt, setPrompt] = useState('')
  const [repoSource, setRepoSource] = useState<RepoSource>('none')
  const [githubRepos, setGithubRepos] = useState<GitHubRepo[]>([])
  const [githubRepoName, setGithubRepoName] = useState('')
  const [repoQuery, setRepoQuery] = useState('')
  const [localPath, setLocalPath] = useState('')
  const [browsePath, setBrowsePath] = useState('/opt/workstation/repos')
  const [browseEntries, setBrowseEntries] = useState<BrowseEntry[]>([])
  const [loadingRepos, setLoadingRepos] = useState(false)
  const [loadingBrowse, setLoadingBrowse] = useState(false)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')

  const selectedGithubRepo = useMemo(
    () => githubRepos.find(repo => repo.full_name === githubRepoName),
    [githubRepos, githubRepoName],
  )

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

  useEffect(() => {
    if (repoSource === 'github' && githubRepos.length === 0 && !loadingRepos) void loadGithubRepos()
    if (repoSource === 'local' && browseEntries.length === 0 && !loadingBrowse) void browseLocalPath(browsePath)
  }, [repoSource, githubRepos.length, browseEntries.length, loadingRepos, loadingBrowse, loadGithubRepos, browseLocalPath, browsePath])

  const createSession = useCallback(async () => {
    const cleanPrompt = prompt.trim()
    if (!cleanPrompt || creating) return
    setCreating(true)
    setError('')
    try {
      const repoSession = await createOptionalRepositorySessionFromHomeSelection({ repoSource, selectedGithubRepo, localPath })
      const goalSession = await createGoalSessionForHomePrompt(cleanPrompt, repoSession)
      if (repoSession) {
        await mountRepositorySessionUnderGoalSession({
          repoSession,
          goalSession,
          userIntent: `Use ${repoSession.title} as context for: ${cleanPrompt}`,
        })
      }
      onNavigate(`/session/${goalSession.id}`)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setCreating(false)
    }
  }, [prompt, creating, repoSource, selectedGithubRepo, localPath, onNavigate])

  return (
    <PlatformHomeThreePaneShell activeSession={null} onNavigate={onNavigate}>
      <div className="platform-home-centered-card">
        <section className="home-dialog" aria-label="Start a session">
          <div className="home-kicker">Agent workspace</div>
          <h1>What should we work on?</h1>
          <p className="home-subtitle">Start with a prompt. Attach a repository now, or start unscoped and attach one before code execution.</p>
          <PlatformHomeRepositoryScopeSelector repoSource={repoSource} setRepoSource={setRepoSource} repoQuery={repoQuery} setRepoQuery={setRepoQuery} githubRepoName={githubRepoName} setGithubRepoName={setGithubRepoName} githubRepos={githubRepos} localPath={localPath} setLocalPath={setLocalPath} browsePath={browsePath} browseEntries={browseEntries} loadingRepos={loadingRepos} loadingBrowse={loadingBrowse} onLoadGithubRepos={loadGithubRepos} onBrowseLocalPath={browseLocalPath} />
          <div className="home-composer">
            <textarea value={prompt} onChange={event => setPrompt(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void createSession() } }} placeholder="Describe the feature, bug, review, or question..." rows={5} autoFocus />
            <button type="button" className="home-send" onClick={createSession} disabled={!prompt.trim() || creating} aria-label="Create session">{creating ? <Loader2 size={19} className="spin" /> : <ArrowUp size={20} />}</button>
          </div>
          {repoSource === 'none' && <p className="home-note">Repo is optional at session start. The platform should require one only before repo-dependent execution.</p>}
          {error && <div className="home-error">{error}</div>}
        </section>
      </div>
    </PlatformHomeThreePaneShell>
  )
}
