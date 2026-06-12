type RepoSource = {
  service: string
  enabled: boolean
  repo_provider?: string
  owner?: string | null
  repo?: string | null
  repo_url?: string | null
  branch?: string | null
  path?: string | null
}

type RepoSourceResponse = {
  services: Record<string, RepoSource>
}

const REPO_SOURCE_API = window.location.port === '5173'
  ? `${window.location.protocol}//${window.location.hostname}:9877/api`
  : '/api'

let sourceCache: Record<string, RepoSource> = {}
let sourceMessage = ''
let sourceMessageTone: 'info' | 'success' | 'error' = 'info'

function sourcePanelRoot(): HTMLElement | null {
  let root = document.querySelector('.repo-source-panel') as HTMLElement | null
  if (root) return root
  const providerPanel = document.querySelector('.repo-provider-panel')
  const portManager = document.querySelector('.port-manager')
  const anchor = providerPanel || portManager
  if (!anchor?.parentElement) return null
  root = document.createElement('section')
  root.className = 'repo-source-panel'
  anchor.insertAdjacentElement(providerPanel ? 'afterend' : 'beforebegin', root)
  return root
}

async function readRepoJson<T>(response: Response): Promise<T> {
  const text = await response.text()
  if (!text) return {} as T
  return JSON.parse(text) as T
}

async function repoSourceApi<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${REPO_SOURCE_API}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    cache: 'no-store',
  })
  const data = await readRepoJson<T & { detail?: any; error?: { message?: string } }>(response)
  if (!response.ok) {
    const detail = (data as any).detail
    const message = (data as any).error?.message || detail?.error?.message || (typeof detail === 'string' ? detail : '') || `${response.status} ${response.statusText}`
    throw new Error(message)
  }
  return data as T
}

function setSourceMessage(message: string, tone: 'info' | 'success' | 'error' = 'info'): void {
  sourceMessage = message
  sourceMessageTone = tone
  renderRepoSources()
}

async function loadRepoSources(): Promise<void> {
  try {
    const data = await repoSourceApi<RepoSourceResponse>('/repo-sources')
    sourceCache = data.services || {}
    sourceMessage = ''
    renderRepoSources()
  } catch (error) {
    setSourceMessage(error instanceof Error ? error.message : 'Unable to load repo sources.', 'error')
  }
}

function inputValue(root: HTMLElement, service: string, field: string): string {
  const input = root.querySelector(`[data-service="${service}"][data-field="${field}"]`) as HTMLInputElement | null
  return input?.value.trim() || ''
}

async function saveRepoSource(service: string): Promise<void> {
  const root = sourcePanelRoot()
  if (!root) return
  const enabled = (root.querySelector(`[data-service="${service}"][data-field="enabled"]`) as HTMLInputElement | null)?.checked ?? true
  const payload = {
    enabled,
    repo_provider: inputValue(root, service, 'repo_provider') || 'github',
    owner: inputValue(root, service, 'owner') || null,
    repo: inputValue(root, service, 'repo') || null,
    repo_url: inputValue(root, service, 'repo_url') || null,
    branch: inputValue(root, service, 'branch') || null,
    path: inputValue(root, service, 'path') || null,
  }
  try {
    const data = await repoSourceApi<{ ok: boolean; service: RepoSource }>(`/repo-sources/${encodeURIComponent(service)}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    })
    sourceCache[service] = data.service
    setSourceMessage(`Saved repo source for ${service}.`, 'success')
  } catch (error) {
    setSourceMessage(error instanceof Error ? error.message : `Unable to save ${service}.`, 'error')
  }
}

async function resetRepoSource(service: string): Promise<void> {
  try {
    const data = await repoSourceApi<{ ok: boolean; service: RepoSource }>(`/repo-sources/${encodeURIComponent(service)}/reset`, { method: 'POST' })
    sourceCache[service] = data.service
    setSourceMessage(`Reset repo source for ${service}.`, 'success')
  } catch (error) {
    setSourceMessage(error instanceof Error ? error.message : `Unable to reset ${service}.`, 'error')
  }
}

function renderRepoSources(): void {
  const root = sourcePanelRoot()
  if (!root) return
  const sources = Object.values(sourceCache).sort((a, b) => a.service.localeCompare(b.service))
  const rows = sources.map(source => `
    <article class="rsp-row">
      <div class="rsp-row-head">
        <strong>${source.service}</strong>
        <label class="rsp-enabled"><input type="checkbox" data-service="${source.service}" data-field="enabled" ${source.enabled !== false ? 'checked' : ''}> enabled</label>
      </div>
      <div class="rsp-grid">
        <label><span>Provider</span><input data-service="${source.service}" data-field="repo_provider" value="${source.repo_provider || 'github'}"></label>
        <label><span>Owner</span><input data-service="${source.service}" data-field="owner" value="${source.owner || ''}" placeholder="owner/org"></label>
        <label><span>Repo</span><input data-service="${source.service}" data-field="repo" value="${source.repo || ''}" placeholder="repo name"></label>
        <label><span>Branch</span><input data-service="${source.service}" data-field="branch" value="${source.branch || ''}" placeholder="default branch"></label>
        <label class="rsp-wide"><span>Local path</span><input data-service="${source.service}" data-field="path" value="${source.path || ''}"></label>
        <label class="rsp-wide"><span>Explicit repo URL override</span><input data-service="${source.service}" data-field="repo_url" value="${source.repo_url || ''}" placeholder="optional; generated from owner/repo when blank"></label>
      </div>
      <div class="rsp-actions">
        <button class="rsp-btn rsp-save" data-service="${source.service}" type="button">Save source</button>
        <button class="rsp-btn rsp-reset" data-service="${source.service}" type="button">Reset default</button>
      </div>
    </article>
  `).join('')

  root.innerHTML = `
    <div class="rsp-head">
      <div>
        <strong>Repo sources</strong>
        <p>Map each service to provider, owner, repo, branch, and local path. Credentials stay in Repo provider.</p>
      </div>
      <button class="rsp-btn rsp-refresh" type="button">Refresh sources</button>
    </div>
    ${sourceMessage ? `<div class="rsp-message ${sourceMessageTone}">${sourceMessage}</div>` : ''}
    <div class="rsp-list">${rows || '<p class="rsp-muted">No repo-backed services configured.</p>'}</div>
  `
}

function handleRepoSourceClick(event: MouseEvent): void {
  const target = event.target as Element | null
  if (!target) return
  const save = target.closest('.rsp-save') as HTMLElement | null
  const reset = target.closest('.rsp-reset') as HTMLElement | null
  if (target.closest('.rsp-refresh')) {
    event.preventDefault()
    void loadRepoSources()
  } else if (save?.dataset.service) {
    event.preventDefault()
    void saveRepoSource(save.dataset.service)
  } else if (reset?.dataset.service) {
    event.preventDefault()
    void resetRepoSource(reset.dataset.service)
  }
}

document.addEventListener('click', handleRepoSourceClick)

const repoSourceObserver = new MutationObserver(() => {
  if (!document.querySelector('.repo-source-panel') && (document.querySelector('.repo-provider-panel') || document.querySelector('.port-manager'))) {
    renderRepoSources()
  }
})
repoSourceObserver.observe(document.body, { childList: true, subtree: true })

void loadRepoSources()
