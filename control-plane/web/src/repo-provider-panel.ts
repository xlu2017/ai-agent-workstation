import './repo-source-panel'

type RepoProviderId = 'personal_access_token' | 'github_oauth' | 'none'

type RepoProvider = {
  id: RepoProviderId
  label: string
  description: string
  configured: boolean
  connected: boolean
  selected: boolean
  requires_login: boolean
  login?: string | null
  username?: string | null
  scopes?: string[]
  connected_at?: string | null
}

type RepoProviderStatus = {
  active_provider: RepoProviderId
  effective_token_available: boolean
  github_oauth_configured: boolean
  providers: RepoProvider[]
}

type LoginUrlResponse = {
  ok: boolean
  login_url?: string
  error?: { code?: string; message?: string }
}

const REPO_PROVIDER_API = window.location.port === '5173'
  ? `${window.location.protocol}//${window.location.hostname}:9877/api`
  : '/api'

let statusCache: RepoProviderStatus | null = null
let message = ''
let messageTone: 'info' | 'success' | 'error' = 'info'

function panelRoot(): HTMLElement | null {
  let root = document.querySelector('.repo-provider-panel') as HTMLElement | null
  if (root) return root
  const portManager = document.querySelector('.port-manager')
  if (!portManager?.parentElement) return null
  root = document.createElement('section')
  root.className = 'repo-provider-panel'
  portManager.parentElement.insertBefore(root, portManager)
  return root
}

async function readJson<T>(response: Response): Promise<T> {
  const text = await response.text()
  if (!text) return {} as T
  return JSON.parse(text) as T
}

function setMessage(next: string, tone: 'info' | 'success' | 'error' = 'info'): void {
  message = next
  messageTone = tone
  render()
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${REPO_PROVIDER_API}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    cache: 'no-store',
  })
  const data = await readJson<T & { error?: { message?: string }; detail?: any }>(response)
  if (!response.ok) {
    const fallback = `${response.status} ${response.statusText}`
    const detail = (data as any).detail
    const detailMessage = typeof detail === 'string' ? detail : detail?.error?.message
    throw new Error((data as any).error?.message || detailMessage || fallback)
  }
  return data as T
}

async function loadStatus(): Promise<void> {
  try {
    statusCache = await api<RepoProviderStatus>('/repo-provider/status')
    message = ''
    render()
  } catch (error) {
    setMessage(error instanceof Error ? error.message : 'Unable to load repo provider status.', 'error')
  }
}

async function selectProvider(provider: RepoProviderId): Promise<void> {
  try {
    statusCache = await api<RepoProviderStatus>('/repo-provider/select', {
      method: 'POST',
      body: JSON.stringify({ provider }),
    })
    setMessage(`Repo provider set to ${provider.replace(/_/g, ' ')}.`, 'success')
  } catch (error) {
    setMessage(error instanceof Error ? error.message : 'Unable to select repo provider.', 'error')
  }
}

async function connectGitHub(): Promise<void> {
  try {
    const redirect = `${window.location.origin}/api/repo-provider/github/callback`
    const data = await api<LoginUrlResponse>(`/repo-provider/github/login-url?redirect_uri=${encodeURIComponent(redirect)}`)
    if (!data.ok || !data.login_url) {
      throw new Error(data.error?.message || 'GitHub login is not configured.')
    }
    window.location.href = data.login_url
  } catch (error) {
    setMessage(error instanceof Error ? error.message : 'Unable to start GitHub login.', 'error')
  }
}

async function disconnectGitHub(): Promise<void> {
  try {
    statusCache = await api<RepoProviderStatus>('/repo-provider/github/disconnect', { method: 'POST' })
    setMessage('GitHub login disconnected.', 'success')
  } catch (error) {
    setMessage(error instanceof Error ? error.message : 'Unable to disconnect GitHub login.', 'error')
  }
}

function providerSummary(provider: RepoProvider): string {
  if (provider.id === 'github_oauth') {
    if (!provider.configured) return 'OAuth app not configured'
    if (provider.connected) return provider.login ? `Connected as ${provider.login}` : 'Connected'
    return 'Not connected'
  }
  if (provider.id === 'personal_access_token') return provider.connected ? 'Environment token available' : 'No environment token'
  return 'Repo operations disabled'
}

function render(): void {
  const root = panelRoot()
  if (!root) return
  const status = statusCache
  if (!status) {
    root.innerHTML = '<div class="rpp-head"><strong>Repo provider</strong><button class="rpp-refresh">Refresh</button></div><p class="rpp-muted">Loading repo provider status…</p>'
    return
  }

  const options = status.providers.map(provider => `
    <option value="${provider.id}" ${provider.selected ? 'selected' : ''}>${provider.label}</option>
  `).join('')
  const providers = status.providers.map(provider => `
    <article class="rpp-provider ${provider.selected ? 'is-selected' : ''}">
      <div>
        <strong>${provider.label}</strong>
        <p>${provider.description}</p>
        <small>${providerSummary(provider)}</small>
      </div>
      <span class="rpp-pill ${provider.connected ? 'is-ok' : provider.configured ? 'is-warn' : 'is-bad'}">${provider.connected ? 'connected' : provider.configured ? 'configured' : 'not configured'}</span>
    </article>
  `).join('')
  const github = status.providers.find(provider => provider.id === 'github_oauth')
  const showConnect = github?.configured && !github.connected
  const showDisconnect = github?.connected

  root.innerHTML = `
    <div class="rpp-head">
      <div>
        <strong>Repo provider</strong>
        <p>Choose which server-side credential backs Check Latest and Update Latest.</p>
      </div>
      <span class="rpp-pill ${status.effective_token_available ? 'is-ok' : 'is-bad'}">${status.effective_token_available ? 'token available' : 'no token'}</span>
    </div>
    <div class="rpp-controls">
      <label>
        <span>Active provider</span>
        <select class="rpp-select">${options}</select>
      </label>
      <button class="rpp-btn rpp-refresh" type="button">Refresh</button>
      ${showConnect ? '<button class="rpp-btn rpp-primary rpp-connect" type="button">Login with GitHub</button>' : ''}
      ${showDisconnect ? '<button class="rpp-btn rpp-disconnect" type="button">Disconnect GitHub</button>' : ''}
    </div>
    ${message ? `<div class="rpp-message ${messageTone}">${message}</div>` : ''}
    <div class="rpp-provider-grid">${providers}</div>
  `
}

function handleClick(event: MouseEvent): void {
  const target = event.target as Element | null
  if (!target) return
  if (target.closest('.rpp-refresh')) {
    event.preventDefault()
    void loadStatus()
  }
  if (target.closest('.rpp-connect')) {
    event.preventDefault()
    void connectGitHub()
  }
  if (target.closest('.rpp-disconnect')) {
    event.preventDefault()
    void disconnectGitHub()
  }
}

function handleChange(event: Event): void {
  const target = event.target as HTMLSelectElement | null
  if (!target?.classList.contains('rpp-select')) return
  void selectProvider(target.value as RepoProviderId)
}

document.addEventListener('click', handleClick)
document.addEventListener('change', handleChange)

const observer = new MutationObserver(() => {
  if (!document.querySelector('.repo-provider-panel') && document.querySelector('.port-manager')) {
    render()
  }
})
observer.observe(document.body, { childList: true, subtree: true })

void loadStatus()
