type Json = Record<string, any>

type SessionGraphSession = {
  id: string
  kind: string
  title: string
  summary?: string
  status: string
  parent_id?: string | null
  root_id?: string | null
  facets?: Json
  state?: Json
  metadata?: Json
}

type SessionGraphEdge = {
  id: string
  type: string
  source_session_id: string
  target_session_id: string
  metadata?: Json
}

type Topology = {
  root_session_id: string
  backend: Json
  frontends: Json[]
  isolation_mode: string
  traces?: Json[]
  updated_at?: string
}

const API_ROOT = window.location.port === '5173'
  ? `${window.location.protocol}//${window.location.hostname}:9877/api`
  : '/api'

function api(path: string): string {
  return `${API_ROOT}${path.startsWith('/') ? path : `/${path}`}`
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(api(path), {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  })
  if (!response.ok) throw new Error(await response.text() || `${response.status} ${response.statusText}`)
  return response.json() as Promise<T>
}

function node<K extends keyof HTMLElementTagNameMap>(tag: K, className = '', text = ''): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag)
  if (className) el.className = className
  if (text) el.textContent = text
  return el
}

function input(label: string, value: string): HTMLLabelElement {
  const wrap = node('label', 'mf-field')
  const span = node('span', '', label)
  const box = node('input')
  box.value = value
  wrap.append(span, box)
  return wrap
}

function makeDevice(label: string, os: string, runtime: string, width: number, height: number, extra: Json = {}): Json {
  return { label, os_family: os, runtime_kind: runtime, viewport_width: width, viewport_height: height, ...extra }
}

function makeFrontend(label: string, device_profile: Json, backendId: string, baseUrl: string, currentUrl: string): Json {
  return {
    label,
    device_profile,
    backend_instance_id: backendId,
    target_base_url: baseUrl,
    health: 'unknown',
    current_url: currentUrl,
    auth_identity: `${label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}-user@example.test`,
  }
}

function topologyFromSession(session: SessionGraphSession): Topology | null {
  const topology = session.state?.multi_frontend_topology
  if (!topology || typeof topology !== 'object') return null
  return topology as Topology
}

async function snapshot(): Promise<{ sessions: SessionGraphSession[]; edges: SessionGraphEdge[] }> {
  const data = await requestJson<{ graph: { sessions: SessionGraphSession[]; edges: SessionGraphEdge[] } }>('/session-graph/snapshot')
  return { sessions: data.graph.sessions || [], edges: data.graph.edges || [] }
}

async function postSession(session: Json): Promise<SessionGraphSession> {
  const data = await requestJson<{ session: SessionGraphSession }>('/session-graph/sessions', { method: 'POST', body: JSON.stringify(session) })
  return data.session
}

async function patchSession(sessionId: string, patch: Json): Promise<SessionGraphSession> {
  const data = await requestJson<{ session: SessionGraphSession }>(`/session-graph/sessions/${encodeURIComponent(sessionId)}`, { method: 'PATCH', body: JSON.stringify(patch) })
  return data.session
}

async function postEdge(type: string, source: string, target: string, metadata: Json): Promise<void> {
  await requestJson('/session-graph/edges', { method: 'POST', body: JSON.stringify({ type, source_session_id: source, target_session_id: target, metadata }) })
}

async function createTopologyViaCrud(title: string, baseUrl: string): Promise<Topology> {
  const backend = { id: `backend-${Date.now()}`, label: 'API', base_url: baseUrl, health: 'unknown', port: Number(new URL(baseUrl).port || 0) || null }
  const frontends = [
    makeFrontend('Chrome desktop', makeDevice('Chrome desktop', 'web', 'browser', 1440, 900, { browser_name: 'chrome' }), backend.id, baseUrl, `${baseUrl}/`),
    makeFrontend('Android emulator', makeDevice('Pixel emulator', 'android', 'emulator', 412, 915, { emulator_name: 'pixel-8' }), backend.id, baseUrl, `${baseUrl}/`),
    makeFrontend('iOS simulator', makeDevice('iOS simulator', 'ios', 'simulator', 390, 844, { emulator_name: 'iphone' }), backend.id, baseUrl, `${baseUrl}/`),
  ]
  const root = await postSession({
    kind: 'app',
    title,
    summary: 'Multi-frontend app session with one shared backend and isolated frontend clients.',
    status: 'active',
    facets: { app: { multi_frontend: true, isolation_mode: 'shared_backend_separate_user' } },
    state: {},
    metadata: { created_by: 'multi_frontend_panel' },
  })
  const backendSession = await postSession({
    kind: 'runtime',
    title: `Backend: ${backend.label}`,
    summary: 'Shared backend runtime for multi-frontend processing.',
    status: 'active',
    parent_id: root.id,
    root_id: root.id,
    facets: { runtime: { role: 'backend', backend_instance: backend } },
    state: { health: backend.health, base_url: backend.base_url },
    metadata: { multi_frontend_role: 'backend' },
  })
  backend.session_id = backendSession.id
  const frontendSessions: SessionGraphSession[] = []
  for (const frontend of frontends) {
    const session = await postSession({
      kind: 'runtime',
      title: `Frontend: ${frontend.label}`,
      summary: 'Isolated frontend client connected to the shared backend.',
      status: 'active',
      parent_id: root.id,
      root_id: root.id,
      facets: { runtime: { role: 'frontend_client', frontend_instance: frontend } },
      state: { health: frontend.health, current_url: frontend.current_url, target_base_url: frontend.target_base_url },
      metadata: { multi_frontend_role: 'frontend', backend_instance_id: backend.id, device_profile_id: frontend.device_profile.id || frontend.device_profile.label },
    })
    frontend.session_id = session.id
    frontendSessions.push(session)
  }
  await postEdge('contains', root.id, backendSession.id, { relationship: 'app_has_shared_backend' })
  for (const session of frontendSessions) {
    await postEdge('contains', root.id, session.id, { relationship: 'app_has_frontend_client' })
    await postEdge('depends_on', session.id, backendSession.id, { relationship: 'frontend_uses_shared_backend' })
  }
  const topology: Topology = { root_session_id: root.id, backend, frontends, isolation_mode: 'shared_backend_separate_user', traces: [], updated_at: new Date().toISOString() }
  await patchSession(root.id, { state: { multi_frontend_topology: topology }, reason: 'Store multi-frontend topology created from UI.' })
  return topology
}

async function createTopology(title: string, baseUrl: string): Promise<Topology> {
  const backend = { label: 'API', base_url: baseUrl, health: 'unknown', port: Number(new URL(baseUrl).port || 0) || null }
  const frontends = [
    makeFrontend('Chrome desktop', makeDevice('Chrome desktop', 'web', 'browser', 1440, 900, { browser_name: 'chrome' }), backend.id || 'backend', baseUrl, `${baseUrl}/`),
    makeFrontend('Android emulator', makeDevice('Pixel emulator', 'android', 'emulator', 412, 915, { emulator_name: 'pixel-8' }), backend.id || 'backend', baseUrl, `${baseUrl}/`),
    makeFrontend('iOS simulator', makeDevice('iOS simulator', 'ios', 'simulator', 390, 844, { emulator_name: 'iphone' }), backend.id || 'backend', baseUrl, `${baseUrl}/`),
  ]
  try {
    const data = await requestJson<{ topology: Topology }>('/multi-frontend/topologies', {
      method: 'POST',
      body: JSON.stringify({ app_title: title, intent: 'Process multiple frontends against one backend.', backend, frontends, isolation_mode: 'shared_backend_separate_user' }),
    })
    return data.topology
  } catch (_) {
    return createTopologyViaCrud(title, baseUrl)
  }
}

function buildMatrix(topology: Topology): HTMLTableElement {
  const table = node('table', 'mf-table')
  table.innerHTML = '<thead><tr><th>Frontend</th><th>OS</th><th>Runtime</th><th>URL</th><th>Health</th><th>Latest trace</th></tr></thead>'
  const body = node('tbody')
  for (const frontend of topology.frontends || []) {
    const row = node('tr')
    row.innerHTML = `<td>${frontend.label || ''}</td><td>${frontend.device_profile?.os_family || ''}</td><td>${frontend.device_profile?.runtime_kind || ''}</td><td>${frontend.current_url || ''}</td><td>${frontend.health || 'unknown'}</td><td>${frontend.latest_trace_id || 'none'}</td>`
    body.append(row)
  }
  table.append(body)
  return table
}

async function registerDemoTrace(topology: Topology): Promise<void> {
  const frontend = topology.frontends[0]
  if (!frontend) return
  const traceId = `trace-${Date.now()}`
  try {
    await requestJson('/multi-frontend/traces', {
      method: 'POST',
      body: JSON.stringify({ root_session_id: topology.root_session_id, backend_instance_id: topology.backend.id, frontend_instance_id: frontend.id, trace_id: traceId, method: 'GET', url: '/', status_code: 200, backend_route: 'demo.root', user_flow_id: 'demo-flow' }),
    })
    return
  } catch (_) {
    // Fallback uses generic session graph state patch.
  }
  const updated = structuredClone(topology)
  updated.traces = [...(updated.traces || []), { id: `trace-${Date.now()}`, root_session_id: topology.root_session_id, backend_instance_id: topology.backend.id, frontend_instance_id: frontend.id, trace_id: traceId, method: 'GET', url: '/', status_code: 200, backend_route: 'demo.root', user_flow_id: 'demo-flow', created_at: new Date().toISOString() }]
  updated.frontends = updated.frontends.map((item) => item.id === frontend.id ? { ...item, latest_trace_id: traceId } : item)
  updated.updated_at = new Date().toISOString()
  await patchSession(topology.root_session_id, { state: { multi_frontend_topology: updated }, reason: 'Register demo multi-frontend trace from UI.' })
}

function renderTopology(container: HTMLElement, topology: Topology): void {
  container.innerHTML = ''
  const head = node('div', 'mf-summary')
  head.innerHTML = `<strong>${topology.backend?.label || 'Backend'}</strong><span>${topology.backend?.base_url || ''}</span><span>${topology.isolation_mode}</span><span>${(topology.traces || []).length} trace(s)</span>`
  const actions = node('div', 'mf-actions')
  const trace = node('button', 'mf-btn', 'Register demo trace')
  trace.onclick = async () => { await registerDemoTrace(topology); await refreshPanel(container.closest('.mf-panel') as HTMLElement) }
  actions.append(trace)
  container.append(head, buildMatrix(topology), actions)
}

async function refreshPanel(panel: HTMLElement): Promise<void> {
  const matrix = panel.querySelector<HTMLElement>('[data-mf-matrix]')!
  const status = panel.querySelector<HTMLElement>('[data-mf-status]')!
  status.textContent = 'Loading topology…'
  try {
    const snap = await snapshot()
    const sessions = snap.sessions.filter((session) => topologyFromSession(session))
    if (!sessions.length) {
      matrix.innerHTML = '<div class="mf-empty">No multi-frontend topology exists yet.</div>'
      status.textContent = 'Ready'
      return
    }
    const topology = topologyFromSession(sessions[sessions.length - 1])!
    renderTopology(matrix, topology)
    status.textContent = `Loaded ${sessions.length} topology record(s)`
  } catch (error) {
    matrix.innerHTML = `<div class="mf-error">${(error as Error).message}</div>`
    status.textContent = 'Error'
  }
}

function installPanel(): void {
  if (document.getElementById('mf-launcher')) return
  const launcher = node('button', 'mf-launcher', 'Multi-frontend')
  launcher.id = 'mf-launcher'
  const panel = node('section', 'mf-panel mf-hidden')
  panel.innerHTML = `<header><strong>Multi-frontend shared backend</strong><button data-mf-close>×</button></header><div class="mf-body"><p>Coordinate desktop browsers and OS emulators against one backend session.</p><div data-mf-form></div><div data-mf-status class="mf-status">Ready</div><div data-mf-matrix></div></div>`
  const form = panel.querySelector<HTMLElement>('[data-mf-form]')!
  const title = input('App session title', 'Multi-client app')
  const base = input('Backend base URL', `${window.location.protocol}//${window.location.hostname}:8080`)
  const create = node('button', 'mf-btn mf-primary', 'Create demo topology')
  create.onclick = async () => {
    const status = panel.querySelector<HTMLElement>('[data-mf-status]')!
    status.textContent = 'Creating topology…'
    try {
      await createTopology(title.querySelector('input')!.value || 'Multi-client app', base.querySelector('input')!.value || 'http://127.0.0.1:8080')
      await refreshPanel(panel)
    } catch (error) {
      status.textContent = (error as Error).message
    }
  }
  const refresh = node('button', 'mf-btn', 'Refresh matrix')
  refresh.onclick = () => refreshPanel(panel)
  form.append(title, base, node('div', 'mf-actions'))
  form.querySelector('.mf-actions')!.append(create, refresh)
  panel.querySelector('[data-mf-close]')!.addEventListener('click', () => panel.classList.add('mf-hidden'))
  launcher.onclick = () => { panel.classList.toggle('mf-hidden'); if (!panel.classList.contains('mf-hidden')) refreshPanel(panel) }
  document.body.append(launcher, panel)
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', installPanel)
else installPanel()
