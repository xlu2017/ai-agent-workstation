import { useCallback, useEffect, useMemo, useState } from 'react'
import { ArrowUp, Check, ChevronDown, Folder, Github, HardDrive, Laptop, Loader2, Monitor, MoreHorizontal, Paperclip, Plus, Search, Smartphone } from 'lucide-react'
import type { BrowseEntry, GitHubRepo, RepoSource } from './types'
import { getControlPlaneJson } from './platformHomeControlPlaneRequestHelpers'
import PlatformHomeThreePaneShell from './PlatformHomeThreePaneShell'
import { createOptionalRepositorySessionFromHomeSelection } from './createOptionalRepositorySessionFromHomeSelection'
import { createGoalSessionForHomePrompt } from './createGoalSessionForHomePrompt'
import { mountRepositorySessionUnderGoalSession } from './mountRepositorySessionUnderGoalSession'
import { displayNameForGitHubRepository, displayNameForLocalRepositoryPath } from './platformHomeRepositoryNameHelpers'

type HomeMenu = 'source' | 'repository' | 'runtime' | 'attachments' | 'more' | null
type HomeRuntimeId = 'ubuntu' | 'windows' | 'android' | 'ios' | 'macos'

type RuntimeOption = {
  id: HomeRuntimeId
  label: string
  tag?: string
  description: string
}

const runtimeOptions: RuntimeOption[] = [
  { id: 'ubuntu', label: 'Ubuntu', description: 'Default workstation runtime' },
  { id: 'windows', label: 'Windows', tag: 'emulator', description: 'Windows app and browser automation target' },
  { id: 'android', label: 'Android', tag: 'emulator', description: 'Android mobile app automation target' },
  { id: 'ios', label: 'iOS', tag: 'emulator', description: 'iOS mobile app automation target' },
  { id: 'macos', label: 'macOS', tag: 'emulator', description: 'macOS desktop automation target' },
]

export default function PlatformHomeInitialChatScreen({ onNavigate }: { onNavigate: (path: string) => void }) {
  const [prompt, setPrompt] = useState('')
  const [repoSource, setRepoSource] = useState<RepoSource>('github')
  const [githubRepos, setGithubRepos] = useState<GitHubRepo[]>([])
  const [githubRepoName, setGithubRepoName] = useState('')
  const [repoQuery, setRepoQuery] = useState('')
  const [localPath, setLocalPath] = useState('')
  const [browsePath, setBrowsePath] = useState('/opt/workstation/repos')
  const [browseEntries, setBrowseEntries] = useState<BrowseEntry[]>([])
  const [runtimeId, setRuntimeId] = useState<HomeRuntimeId>('ubuntu')
  const [openMenu, setOpenMenu] = useState<HomeMenu>(null)
  const [loadingRepos, setLoadingRepos] = useState(false)
  const [loadingBrowse, setLoadingBrowse] = useState(false)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')

  const selectedGithubRepo = useMemo(
    () => githubRepos.find(repo => repo.full_name === githubRepoName),
    [githubRepos, githubRepoName],
  )

  const selectedRuntime = useMemo(
    () => runtimeOptions.find(option => option.id === runtimeId) || runtimeOptions[0],
    [runtimeId],
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

  const changeRepoSource = useCallback((nextSource: RepoSource) => {
    setRepoSource(nextSource)
    setOpenMenu(null)
    if (nextSource === 'github' && githubRepos.length === 0 && !loadingRepos) void loadGithubRepos()
    if (nextSource === 'local' && browseEntries.length === 0 && !loadingBrowse) void browseLocalPath(browsePath)
  }, [browseEntries.length, browseLocalPath, browsePath, githubRepos.length, loadGithubRepos, loadingBrowse, loadingRepos])

  const createSession = useCallback(async () => {
    const cleanPrompt = prompt.trim()
    if (!cleanPrompt || creating) return
    setCreating(true)
    setError('')
    try {
      const repoSession = await createOptionalRepositorySessionFromHomeSelection({ repoSource, selectedGithubRepo, localPath })
      const goalSession = await createGoalSessionForHomePrompt(cleanPrompt, repoSession, { runtime: runtimeId, repoSource })
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
  }, [prompt, creating, repoSource, selectedGithubRepo, localPath, runtimeId, onNavigate])

  const repositoryLabel = repoSource === 'github'
    ? selectedGithubRepo ? displayNameForGitHubRepository(selectedGithubRepo) : loadingRepos ? 'Loading repositories' : 'Select repository'
    : localPath.trim() ? displayNameForLocalRepositoryPath(localPath) : 'Select local folder'

  return (
    <PlatformHomeThreePaneShell activeSession={null} onNavigate={onNavigate}>
      <div className="platform-home-centered-card devin-home-centered-card">
        <div className="home-devin-mark" aria-hidden="true"><span /><span /><span /></div>
        <section className="home-devin-launcher" aria-label="Start a session">
          <div className="home-devin-composer">
            <textarea value={prompt} onChange={event => setPrompt(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void createSession() } }} placeholder="Ask Agent to build features, fix bugs, or work on your code" rows={5} autoFocus />
            <div className="home-composer-toolbar">
              <div className="home-toolbar-left">
                <div className="home-toolbar-item">
                  <button type="button" className="home-pill-button" onClick={() => setOpenMenu(openMenu === 'source' ? null : 'source')} aria-expanded={openMenu === 'source'}>
                    {repoSource === 'github' ? <Github size={16} /> : <HardDrive size={16} />}
                    <span>{repoSource === 'github' ? 'GitHub' : 'Workstation'}</span>
                    <ChevronDown size={15} />
                  </button>
                  {openMenu === 'source' && <SourcePopover repoSource={repoSource} onSelect={changeRepoSource} />}
                </div>
                <div className="home-toolbar-item">
                  <button type="button" className="home-icon-button" onClick={() => setOpenMenu(openMenu === 'attachments' ? null : 'attachments')} aria-label="Open attachment menu" aria-expanded={openMenu === 'attachments'}><Plus size={20} /></button>
                  {openMenu === 'attachments' && <AttachmentsPopover />}
                </div>
                <div className="home-toolbar-item">
                  <button type="button" className="home-icon-button muted" onClick={() => setOpenMenu(openMenu === 'more' ? null : 'more')} aria-label="Open more menu" aria-expanded={openMenu === 'more'}><MoreHorizontal size={20} /></button>
                  {openMenu === 'more' && <MorePopover />}
                </div>
              </div>
              <button type="button" className="home-send" onClick={createSession} disabled={!prompt.trim() || creating} aria-label="Create session">{creating ? <Loader2 size={19} className="spin" /> : <ArrowUp size={20} />}</button>
            </div>
          </div>
          <div className="home-context-row">
            <div className="home-context-item">
              <button type="button" className="home-context-button" onClick={() => setOpenMenu(openMenu === 'repository' ? null : 'repository')} aria-expanded={openMenu === 'repository'}>
                <Folder size={17} />
                <span>{repositoryLabel}</span>
              </button>
              {openMenu === 'repository' && <RepositoryPopover repoSource={repoSource} repoQuery={repoQuery} setRepoQuery={setRepoQuery} githubRepos={githubRepos} githubRepoName={githubRepoName} setGithubRepoName={setGithubRepoName} localPath={localPath} setLocalPath={setLocalPath} browsePath={browsePath} browseEntries={browseEntries} loadingRepos={loadingRepos} loadingBrowse={loadingBrowse} onLoadGithubRepos={loadGithubRepos} onBrowseLocalPath={browseLocalPath} onClose={() => setOpenMenu(null)} />}
            </div>
            <div className="home-context-item">
              <button type="button" className="home-context-button" onClick={() => setOpenMenu(openMenu === 'runtime' ? null : 'runtime')} aria-expanded={openMenu === 'runtime'}>
                <RuntimeIcon id={selectedRuntime.id} />
                <span>{selectedRuntime.label}</span>
                {selectedRuntime.tag && <small>{selectedRuntime.tag}</small>}
                <ChevronDown size={15} />
              </button>
              {openMenu === 'runtime' && <RuntimePopover runtimeId={runtimeId} onSelect={nextRuntimeId => { setRuntimeId(nextRuntimeId); setOpenMenu(null) }} />}
            </div>
          </div>
          {error && <div className="home-error">{error}</div>}
        </section>
      </div>
    </PlatformHomeThreePaneShell>
  )
}

function SourcePopover({ repoSource, onSelect }: { repoSource: RepoSource; onSelect: (value: RepoSource) => void }) {
  return (
    <div className="home-popover home-source-popover">
      <button type="button" className="home-popover-option" onClick={() => onSelect('github')}>
        <Github size={18} />
        <span><strong>GitHub</strong><small>Source repositories from GitHub</small></span>
        {repoSource === 'github' && <Check size={16} />}
      </button>
      <button type="button" className="home-popover-option" onClick={() => onSelect('local')}>
        <HardDrive size={18} />
        <span><strong>Workstation</strong><small>Source local folders from the machine</small></span>
        {repoSource === 'local' && <Check size={16} />}
      </button>
    </div>
  )
}

function RepositoryPopover(props: {
  repoSource: RepoSource
  repoQuery: string
  setRepoQuery: (value: string) => void
  githubRepos: GitHubRepo[]
  githubRepoName: string
  setGithubRepoName: (value: string) => void
  localPath: string
  setLocalPath: (value: string) => void
  browsePath: string
  browseEntries: BrowseEntry[]
  loadingRepos: boolean
  loadingBrowse: boolean
  onLoadGithubRepos: () => void
  onBrowseLocalPath: (path: string) => void
  onClose: () => void
}) {
  if (props.repoSource === 'local') return <WorkstationRepositoryPopover {...props} />
  const query = props.repoQuery.trim().toLowerCase()
  const visibleRepos = query ? props.githubRepos.filter(repo => displayNameForGitHubRepository(repo).toLowerCase().includes(query)) : props.githubRepos
  const recentRepos = visibleRepos.slice(0, 4)
  const remainingRepos = visibleRepos.slice(4)

  return (
    <div className="home-popover home-repository-popover">
      <div className="home-popover-search"><Search size={16} /><input value={props.repoQuery} onChange={event => props.setRepoQuery(event.target.value)} placeholder="Search for a repository" /><button type="button" onClick={props.onLoadGithubRepos} disabled={props.loadingRepos}>{props.loadingRepos ? 'Loading…' : 'Refresh'}</button></div>
      <div className="home-popover-scroll">
        <div className="home-popover-section-label">Recent</div>
        {recentRepos.length === 0 && <div className="home-empty-row">No repositories found.</div>}
        {recentRepos.map(repo => <GitHubRepositoryRow key={repo.full_name || repo.id} repo={repo} selected={props.githubRepoName === repo.full_name} onSelect={() => { props.setGithubRepoName(repo.full_name || ''); props.onClose() }} />)}
        {remainingRepos.length > 0 && <div className="home-popover-section-label">All repositories</div>}
        {remainingRepos.map(repo => <GitHubRepositoryRow key={repo.full_name || repo.id} repo={repo} selected={props.githubRepoName === repo.full_name} onSelect={() => { props.setGithubRepoName(repo.full_name || ''); props.onClose() }} />)}
      </div>
      <button type="button" className="home-popover-footer"><Plus size={16} /> Add repositories</button>
    </div>
  )
}

function GitHubRepositoryRow({ repo, selected, onSelect }: { repo: GitHubRepo; selected: boolean; onSelect: () => void }) {
  return (
    <button type="button" className="home-repo-row" onClick={onSelect}>
      <span className={selected ? 'home-checkbox checked' : 'home-checkbox'}>{selected && <Check size={13} />}</span>
      <span className="home-repo-main"><strong>{displayNameForGitHubRepository(repo)}</strong>{repo.private && <small>private</small>}</span>
      <span className="home-repo-owner">GitHub</span>
    </button>
  )
}

function WorkstationRepositoryPopover(props: Parameters<typeof RepositoryPopover>[0]) {
  return (
    <div className="home-popover home-repository-popover local">
      <div className="home-popover-search"><Folder size={16} /><input value={props.localPath} onChange={event => props.setLocalPath(event.target.value)} placeholder="/opt/workstation/repos/my-repo" /><button type="button" onClick={() => props.onBrowseLocalPath(props.localPath || props.browsePath)} disabled={props.loadingBrowse}>{props.loadingBrowse ? 'Loading…' : 'Browse'}</button></div>
      <div className="home-local-details">
        <div className="home-browser-path">{props.browsePath}</div>
        {props.browseEntries.slice(0, 10).map(entry => (
          <button key={entry.path} type="button" className="home-repo-row" onClick={() => entry.is_repo ? (props.setLocalPath(entry.path), props.onClose()) : props.onBrowseLocalPath(entry.path)}>
            <span className="home-checkbox"><Folder size={13} /></span>
            <span className="home-repo-main"><strong>{entry.name}</strong><small>{entry.path}</small></span>
            {entry.is_repo && <span className="home-repo-owner">repo</span>}
          </button>
        ))}
        {!props.loadingBrowse && props.browseEntries.length === 0 && <div className="home-empty-row">No local folders found.</div>}
      </div>
    </div>
  )
}

function RuntimePopover({ runtimeId, onSelect }: { runtimeId: HomeRuntimeId; onSelect: (value: HomeRuntimeId) => void }) {
  return (
    <div className="home-popover home-runtime-popover">
      {runtimeOptions.map(option => (
        <button key={option.id} type="button" className="home-popover-option" onClick={() => onSelect(option.id)}>
          <RuntimeIcon id={option.id} />
          <span><strong>{option.label}{option.tag && <em>{option.tag}</em>}</strong><small>{option.description}</small></span>
          {runtimeId === option.id && <Check size={16} />}
        </button>
      ))}
    </div>
  )
}

function AttachmentsPopover() {
  return (
    <div className="home-popover home-compact-popover">
      <button type="button" className="home-popover-option"><Paperclip size={17} /><span><strong>Attachments</strong><small>Add local context files to the prompt</small></span></button>
    </div>
  )
}

function MorePopover() {
  const items = ['Manage MCP connectors', 'Improve prompt', 'Schedule agent', 'Copy prompt as link', 'Record voice prompt', 'Use Imperative Environment', 'Auto-approve starting child sessions', 'Send to Slack Channel']
  return (
    <div className="home-popover home-more-popover">
      {items.map(item => <button key={item} type="button" className="home-popover-option disabled" disabled><span><strong>{item}{item === 'Use Imperative Environment' && <em>Legacy</em>}</strong></span></button>)}
    </div>
  )
}

function RuntimeIcon({ id }: { id: HomeRuntimeId }) {
  if (id === 'android' || id === 'ios') return <Smartphone size={17} />
  if (id === 'macos') return <Laptop size={17} />
  return <Monitor size={17} />
}
