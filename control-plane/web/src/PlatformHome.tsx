import { useCallback, useEffect, useMemo, useState } from 'react'
import { ArrowUp, Folder, GitBranch, Loader2, Search } from 'lucide-react'
import App from './App'
import './platform-home.css'

type RepoSource = 'none' | 'github' | 'local'

type GitHubRepo = {
  id?: number
  name?: string
  full_name?: string
  description?: string | null
  private?: boolean
  default_branch?: string
  clone_url?: string
  ssh_url?: string
  html_url?: string
  updated_at?: string
}

type BrowseEntry = {
  name: string
  path: string
  is_dir: boolean
  is_repo: boolean
}

type GraphSession = {
  id: string
  kind: string
  title: string
  summary?: string
  status?: string
  facets?: Record<string, Record<string, unknown>>
  metadata?: Record<string, unknown>
  created_at?: string
  updated_at?: string
}

const API = window.location.port === '5173'
  ? `${window.location.protocol}//${window.location.hostname}:9877/api`
  : '/api'

function endpoint(path: string): string {
  return `${API}${path.startsWith('/') ? path : `/${path}`}`
}

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(endpoint(path), { cache: 'no-store' })
  const text = await res.text()
  const data = text ? JSON.parse(text) : {}
  if (!res.ok) throw new Error(data?.error?.message || data?.detail || text || `${res.status} ${res.statusText}`)
  return data as T
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(endpoint(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const text = await res.text()
  const data = text ? JSON.parse(text) : {}
  if (!res.ok) throw new Error(data?.error?.message || data?.detail || text || `${res.status} ${res.statusText}`)
  return data as T
}

function titleFromPrompt(prompt: string): string {
  const normalized = prompt.replace(/\s+/g, ' ').trim()
  if (!normalized) return 'New session'
  return normalized.length > 82 ? `${normalized.slice(0, 82)}…` : normalized
}

function repoTitle(repo: GitHubRepo): string {
  return repo.full_name || repo.name || 'GitHub repository'
}

export default function PlatformHome() {
  const [routePath, setRoutePath] = useState(window.location.pathname)

  const navigate = useCallback((path: string) => {
    window.history.pushState({}, '', path)
    setRoutePath(path)
  }, [])

  useEffect(() => {
    const handler = () => setRoutePath(window.location.pathname)
    window.addEventListener('popstate', handler)
    return () => window.removeEventListener('popstate', handler)
  }, [])

  if (routePath === '/') return <HomeStart onNavigate={navigate} />
  if (routePath.startsWith('/session/')) {
    return <GraphSessionWorkspace sessionId={routePath.replace('/session/', '')} onNavigate={navigate} />
  }
  return <App />
}

function HomeStart({ onNavigate }: { onNavigate: (path: string) => void }) {
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

  const filteredGithubRepos = useMemo(() => {
    const query = repoQuery.trim().toLowerCase()
    if (!query) return githubRepos
    return githubRepos.filter(repo => repoTitle(repo).toLowerCase().includes(query))
  }, [githubRepos, repoQuery])

  const loadGithubRepos = useCallback(async () => {
    setLoadingRepos(true)
    try {
      const data = await fetchJson<{ ok: boolean; repositories: GitHubRepo[]; error?: { message?: string } }>('/repo-provider/repositories')
      if (!data.ok) throw new Error(data.error?.message || 'No GitHub repositories are available.')
      setGithubRepos(data.repositories || [])
      setGithubRepoName(current => current || data.repositories?.[0]?.full_name || '')
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoadingRepos(false)
    }
  }, [])

  const loadBrowse = useCallback(async (path = browsePath) => {
    setLoadingBrowse(true)
    try {
      const data = await fetchJson<{ path: string; parent?: string; entries: BrowseEntry[]; error?: string }>(`/browse?path=${encodeURIComponent(path)}`)
      if (data.error) throw new Error(data.error)
      setBrowsePath(data.path)
      setBrowseEntries(data.entries || [])
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoadingBrowse(false)
    }
  }, [browsePath])

  useEffect(() => {
    if (repoSource === 'github' && githubRepos.length === 0 && !loadingRepos) void loadGithubRepos()
    if (repoSource === 'local' && browseEntries.length === 0 && !loadingBrowse) void loadBrowse()
  }, [repoSource, githubRepos.length, browseEntries.length, loadingRepos, loadingBrowse, loadGithubRepos, loadBrowse])

  const createSession = useCallback(async () => {
    const cleanPrompt = prompt.trim()
    if (!cleanPrompt || creating) return
    setCreating(true)
    setError('')
    try {
      let repoSession: GraphSession | null = null

      if (repoSource === 'github' && selectedGithubRepo) {
        const repoResponse = await postJson<{ session: GraphSession }>('/session-graph/sessions', {
          kind: 'repo',
          title: repoTitle(selectedGithubRepo),
          summary: selectedGithubRepo.description || `GitHub repository ${repoTitle(selectedGithubRepo)}`,
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
        repoSession = repoResponse.session
      }

      if (repoSource === 'local' && localPath.trim()) {
        const path = localPath.trim()
        const repoResponse = await postJson<{ session: GraphSession }>('/session-graph/sessions', {
          kind: 'repo',
          title: path.split('/').filter(Boolean).at(-1) || path,
          summary: `Local repository or folder at ${path}`,
          status: 'active',
          facets: { repo: { source: 'local', path, selected_from_home: true } },
          metadata: { created_from: 'home_chat', repo_source: 'local' },
        })
        repoSession = repoResponse.session
      }

      const sessionResponse = await postJson<{ session: GraphSession }>('/session-graph/sessions', {
        kind: 'goal',
        title: titleFromPrompt(cleanPrompt),
        summary: cleanPrompt,
        status: 'active',
        facets: { goal: { initial_prompt: cleanPrompt, repo_optional_at_start: true } },
        state: { initial_prompt: cleanPrompt, chat_turns: [{ role: 'user', content: cleanPrompt }] },
        metadata: {
          created_from: 'home_chat',
          repo_attached_at_start: Boolean(repoSession),
          repo_session_id: repoSession?.id || null,
        },
      })

      const goalSession = sessionResponse.session
      if (repoSession) {
        await postJson('/session-graph/actions/apply', {
          action_name: 'session.mount',
          params: {
            source_session_id: repoSession.id,
            target_session_id: goalSession.id,
            user_intent: `Use ${repoSession.title} as context for: ${cleanPrompt}`,
            mount_mode: 'reference',
            create_adaptation_session: true,
            make_active: true,
          },
        })
      }

      onNavigate(`/session/${goalSession.id}`)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setCreating(false)
    }
  }, [prompt, creating, repoSource, selectedGithubRepo, localPath, onNavigate])

  const submitOnEnter = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void createSession()
    }
  }

  return (
    <main className="platform-home">
      <section className="home-dialog" aria-label="Start a session">
        <div className="home-kicker">Agent workspace</div>
        <h1>What should we work on?</h1>
        <p className="home-subtitle">Start with a prompt. Attach a repository now, or start unscoped and attach one before code execution.</p>

        <div className="home-repo-controls">
          <label className="home-field compact">
            <span>Repository scope</span>
            <select value={repoSource} onChange={event => setRepoSource(event.target.value as RepoSource)}>
              <option value="none">No repo yet</option>
              <option value="github">GitHub repository</option>
              <option value="local">Local repository or folder</option>
            </select>
          </label>

          {repoSource === 'github' && (
            <div className="home-field wide">
              <span>GitHub repository</span>
              <div className="home-search-row">
                <Search size={15} />
                <input value={repoQuery} onChange={event => setRepoQuery(event.target.value)} placeholder="Filter repositories..." />
                <button type="button" onClick={loadGithubRepos} disabled={loadingRepos}>{loadingRepos ? 'Loading…' : 'Refresh'}</button>
              </div>
              <select value={githubRepoName} onChange={event => setGithubRepoName(event.target.value)}>
                <option value="">Select a GitHub repository</option>
                {filteredGithubRepos.map(repo => <option key={repo.full_name || repo.id} value={repo.full_name}>{repoTitle(repo)}{repo.private ? ' · private' : ''}</option>)}
              </select>
            </div>
          )}

          {repoSource === 'local' && (
            <div className="home-field wide">
              <span>Local path</span>
              <div className="home-search-row">
                <Folder size={15} />
                <input value={localPath} onChange={event => setLocalPath(event.target.value)} placeholder="/opt/workstation/repos/my-repo" />
                <button type="button" onClick={() => loadBrowse(localPath || browsePath)} disabled={loadingBrowse}>{loadingBrowse ? 'Loading…' : 'Browse'}</button>
              </div>
              <div className="home-local-browser">
                <div className="home-browser-path">{browsePath}</div>
                {browseEntries.slice(0, 8).map(entry => (
                  <button key={entry.path} type="button" onClick={() => entry.is_repo ? setLocalPath(entry.path) : loadBrowse(entry.path)}>
                    <Folder size={14} />
                    <span>{entry.name}</span>
                    {entry.is_repo && <small>repo</small>}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="home-composer">
          <textarea
            value={prompt}
            onChange={event => setPrompt(event.target.value)}
            onKeyDown={submitOnEnter}
            placeholder="Describe the feature, bug, review, or question..."
            rows={5}
            autoFocus
          />
          <button type="button" className="home-send" onClick={createSession} disabled={!prompt.trim() || creating} aria-label="Create session">
            {creating ? <Loader2 size={19} className="spin" /> : <ArrowUp size={20} />}
          </button>
        </div>

        {repoSource === 'none' && <p className="home-note">Repo is optional at session start. The platform should require one only before repo-dependent execution.</p>}
        {error && <div className="home-error">{error}</div>}
      </section>
    </main>
  )
}

function GraphSessionWorkspace({ sessionId, onNavigate }: { sessionId: string; onNavigate: (path: string) => void }) {
  const [session, setSession] = useState<GraphSession | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    fetchJson<{ session: GraphSession }>(`/session-graph/sessions/${encodeURIComponent(sessionId)}`)
      .then(data => setSession(data.session))
      .catch(err => setError((err as Error).message))
  }, [sessionId])

  if (error) {
    return <main className="platform-home"><section className="home-dialog"><button className="home-link" onClick={() => onNavigate('/')}>← Home</button><div className="home-error">{error}</div></section></main>
  }

  if (!session) {
    return <main className="platform-home"><section className="home-dialog"><div className="home-kicker">Loading session…</div></section></main>
  }

  const initialPrompt = String(session.state?.initial_prompt || session.facets?.goal?.initial_prompt || session.summary || '')
  const repoAttached = Boolean(session.metadata?.repo_attached_at_start)

  return (
    <main className="graph-session-page">
      <header className="graph-session-header">
        <button className="home-link" onClick={() => onNavigate('/')}>← New session</button>
        <button className="home-link" onClick={() => onNavigate('/session-graph')}>Open graph</button>
      </header>
      <section className="graph-session-card">
        <div className="home-kicker">Graph session</div>
        <h1>{session.title}</h1>
        <div className="graph-session-meta">
          <span>{session.kind}</span>
          <span>{session.status || 'active'}</span>
          <span>{repoAttached ? 'repo attached' : 'unscoped'}</span>
        </div>
        <div className="graph-session-message">
          <strong>Initial prompt</strong>
          <p>{initialPrompt}</p>
        </div>
        <div className="graph-session-next">
          <GitBranch size={16} />
          <span>{repoAttached ? 'Repository context was mounted into this session.' : 'Attach a repository before file edits, tests, runtime work, or PR output.'}</span>
        </div>
      </section>
    </main>
  )
}
