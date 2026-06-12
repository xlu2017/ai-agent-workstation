import { POPULAR_SERVER_APPS, searchServerApps, type ServerAppEntry } from './server-app-catalog'

declare global {
  interface Window {
    __serverAppLauncherInstalled?: boolean
  }
}

type PlatformAppResponse = { applications?: ServerAppEntry[]; apps?: ServerAppEntry[] }

const API = '/api'
const CONTROL_API = window.location.port === '5173'
  ? `${window.location.protocol}//${window.location.hostname}:9877/api`
  : API
const HTML_ENTITIES: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }

let currentApps = POPULAR_SERVER_APPS
let currentQuery = ''
let activeCustomTab: string | null = null
const openedAppTabs = new Map<string, ServerAppEntry>()

function endpoint(path: string): string {
  return `${CONTROL_API}${path.startsWith('/') ? path : `/${path}`}`
}

function currentSessionId(): string | null {
  const match = window.location.pathname.match(/\/session\/([^/?#]+)/)
  return match ? decodeURIComponent(match[1]) : null
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>'"]/g, ch => HTML_ENTITIES[ch] || ch)
}

function rightPane(): HTMLElement | null {
  return document.querySelector('.as-right-pane')
}

function tabStrip(): HTMLElement | null {
  return document.querySelector('.as-right-pane .as-tab-strip')
}

function rightContent(): HTMLElement | null {
  return document.querySelector('.as-right-pane .as-right-content')
}

function remoteFrameUrl(): string {
  const frame = document.querySelector<HTMLIFrameElement>('.as-right-content iframe.remote-frame, .remote-frame')
  return frame?.src || `${window.location.origin}/remote-desktop`
}

function popOutRemoteDesktop(app?: ServerAppEntry): void {
  const url = app ? `${window.location.origin}/remote-desktop?app=${encodeURIComponent(app.id)}` : remoteFrameUrl()
  window.open(url, `remote-desktop-${app?.id || 'desktop'}`, 'noopener,noreferrer,width=1440,height=960')
}

async function fetchPlatformApps(): Promise<void> {
  try {
    const response = await fetch(endpoint('/session-graph/platform-apps'))
    if (!response.ok) return
    const data = await response.json() as PlatformAppResponse
    const apps = data.applications || data.apps || []
    if (Array.isArray(apps) && apps.length) currentApps = apps
  } catch {
    currentApps = POPULAR_SERVER_APPS
  }
}

async function launchApp(app: ServerAppEntry): Promise<void> {
  openedAppTabs.set(app.id, app)
  activeCustomTab = `app:${app.id}`
  ensureTabs()
  renderAppTab(app, 'Opening remote desktop tab...')

  if (app.launchMode === 'remote_desktop_only') {
    renderAppTab(app, 'Remote desktop tab opened. Use Pop out to move it to a separate browser window.')
    return
  }

  const sessionId = currentSessionId()
  if (!sessionId) {
    renderAppTab(app, 'No active session is available, so this app tab is ready but launch was not sent to the server.')
    return
  }

  try {
    renderAppTab(app, 'Sending launch request to the session...')
    const response = await fetch(endpoint(`/sessions/${encodeURIComponent(sessionId)}/chat`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ instruction: app.launchPrompt, execution_mode: 'finite' }),
    })
    if (!response.ok) throw new Error(await response.text() || `${response.status} ${response.statusText}`)
    renderAppTab(app, 'Launch request sent. The app should appear in the remote desktop stream.')
  } catch (err) {
    renderAppTab(app, `Launch request failed: ${(err as Error).message}`)
  }
}

function deactivateCustomTabs(): void {
  activeCustomTab = null
  document.querySelectorAll('.as-app-tab').forEach(tab => tab.classList.remove('as-tab-active'))
}

function activateAppsTab(): void {
  activeCustomTab = 'apps'
  ensureTabs()
  renderAppsPanel()
}

function activateAppTab(app: ServerAppEntry): void {
  activeCustomTab = `app:${app.id}`
  ensureTabs()
  renderAppTab(app)
}

function ensureTabs(): void {
  const strip = tabStrip()
  if (!strip) return

  strip.querySelectorAll<HTMLButtonElement>('.as-tab:not(.as-app-tab)').forEach(button => {
    if (button.dataset.appLauncherBound === 'true') return
    button.dataset.appLauncherBound = 'true'
    button.addEventListener('click', deactivateCustomTabs)
  })

  let appsButton = strip.querySelector<HTMLButtonElement>('[data-app-tab="apps"]')
  if (!appsButton) {
    appsButton = document.createElement('button')
    appsButton.type = 'button'
    appsButton.className = 'as-tab as-app-tab'
    appsButton.dataset.appTab = 'apps'
    appsButton.textContent = 'Apps'
    appsButton.addEventListener('click', activateAppsTab)
    strip.appendChild(appsButton)
  }
  appsButton.classList.toggle('as-tab-active', activeCustomTab === 'apps')

  for (const app of openedAppTabs.values()) {
    let button = strip.querySelector<HTMLButtonElement>(`[data-app-tab="app:${app.id}"]`)
    if (!button) {
      button = document.createElement('button')
      button.type = 'button'
      button.className = 'as-tab as-app-tab as-app-instance-tab'
      button.dataset.appTab = `app:${app.id}`
      button.textContent = app.name
      button.title = `Remote desktop tab for ${app.name}`
      button.addEventListener('click', () => activateAppTab(app))
      strip.appendChild(button)
    }
    button.classList.toggle('as-tab-active', activeCustomTab === `app:${app.id}`)
  }

  const pane = rightPane()
  if (pane && !pane.querySelector('.as-popout-all-remote-tabs')) {
    const header = pane.querySelector('.as-right-header')
    const popout = document.createElement('button')
    popout.type = 'button'
    popout.className = 'as-right-collapse as-popout-all-remote-tabs'
    popout.title = 'Open current remote desktop tab in a new browser window'
    popout.textContent = 'Pop out'
    popout.addEventListener('click', () => {
      if (activeCustomTab?.startsWith('app:')) {
        const app = openedAppTabs.get(activeCustomTab.slice(4))
        popOutRemoteDesktop(app)
        return
      }
      popOutRemoteDesktop()
    })
    header?.appendChild(popout)
  }
}

function renderAppsPanel(): void {
  const content = rightContent()
  if (!content) return
  const results = searchServerApps(currentQuery, currentApps)
  content.innerHTML = `
    <div class="as-app-launcher-panel">
      <div class="as-app-launcher-head">
        <div>
          <strong>Server applications</strong>
          <p>Search common desktop apps and open them as right-panel remote desktop tabs.</p>
        </div>
        <button class="as-action-btn as-app-popout-desktop" type="button">Open desktop window</button>
      </div>
      <input class="as-app-search" placeholder="Search apps, commands, or categories..." value="${escapeHtml(currentQuery)}" />
      <div class="as-app-results">
        ${results.map(app => `
          <div class="as-app-card" data-app-id="${escapeHtml(app.id)}">
            <div class="as-app-card-main">
              <span class="as-app-category">${escapeHtml(app.category)}</span>
              <strong>${escapeHtml(app.name)}</strong>
              <p>${escapeHtml(app.description)}</p>
              <small>${escapeHtml(app.preferredCommands.slice(0, 3).join(' · ') || 'remote desktop')}</small>
            </div>
            <button class="as-action-btn as-app-launch" type="button" data-app-id="${escapeHtml(app.id)}">Open tab</button>
          </div>
        `).join('')}
      </div>
    </div>
  `
  content.querySelector<HTMLInputElement>('.as-app-search')?.addEventListener('input', event => {
    currentQuery = (event.target as HTMLInputElement).value
    renderAppsPanel()
  })
  content.querySelector<HTMLButtonElement>('.as-app-popout-desktop')?.addEventListener('click', () => popOutRemoteDesktop())
  content.querySelectorAll<HTMLButtonElement>('.as-app-launch').forEach(button => {
    button.addEventListener('click', () => {
      const app = currentApps.find(candidate => candidate.id === button.dataset.appId)
      if (app) launchApp(app)
    })
  })
  ensureTabs()
}

function renderAppTab(app: ServerAppEntry, status = 'Remote desktop tab ready.'): void {
  const content = rightContent()
  if (!content) return
  content.innerHTML = `
    <div class="as-app-remote-tab">
      <div class="as-app-launcher-head">
        <div>
          <strong>${escapeHtml(app.name)}</strong>
          <p>${escapeHtml(status)}</p>
        </div>
        <div class="as-app-actions">
          <button class="as-action-btn as-app-relaunch" type="button">Relaunch</button>
          <button class="as-action-btn as-app-popout" type="button">Open in browser window</button>
        </div>
      </div>
      <div class="as-app-remote-frame-note">
        Use the Desktop tab or the popped-out window for the live Guacamole stream. This tab keeps app-specific launch state and actions attached to the session.
      </div>
    </div>
  `
  content.querySelector<HTMLButtonElement>('.as-app-relaunch')?.addEventListener('click', () => launchApp(app))
  content.querySelector<HTMLButtonElement>('.as-app-popout')?.addEventListener('click', () => popOutRemoteDesktop(app))
  ensureTabs()
}

export function installServerAppLauncher(): void {
  if (typeof window === 'undefined' || window.__serverAppLauncherInstalled) return
  window.__serverAppLauncherInstalled = true
  fetchPlatformApps().finally(() => ensureTabs())
  const observer = new MutationObserver(() => ensureTabs())
  observer.observe(document.body, { childList: true, subtree: true })
  window.addEventListener('popstate', () => setTimeout(ensureTabs, 0))
}

installServerAppLauncher()

export {}
