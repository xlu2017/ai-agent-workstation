type ServiceInfo = {
  name: string
  update_in_progress?: boolean
  last_update?: {
    status?: string
    message?: string
    commit?: string
    branch?: string
    timestamp?: string
    error?: { code?: string; message?: string } | null
  } | null
}

type UpdateResponse = {
  ok?: boolean
  service?: string
  deferred?: boolean
  message?: string
  error?: { code?: string; message?: string }
}

const CONTROL_API = window.location.port === '5173'
  ? `${window.location.protocol}//${window.location.hostname}:9877/api`
  : '/api'

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms))
}

function parseErrorPayload(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== 'object') return fallback
  const data = payload as Record<string, any>
  if (typeof data.detail === 'string') return data.detail
  if (data.detail?.error?.message) return data.detail.error.message
  if (data.error?.message) return data.error.message
  if (typeof data.message === 'string') return data.message
  return fallback
}

async function readJson<T>(response: Response): Promise<T> {
  const text = await response.text()
  if (!text) return {} as T
  return JSON.parse(text) as T
}

function findUpdateButton(target: EventTarget | null): HTMLButtonElement | null {
  if (!(target instanceof Element)) return null
  return target.closest('button.pm-btn-update') as HTMLButtonElement | null
}

function findServiceName(button: HTMLButtonElement): string | null {
  const item = button.closest('.pm-item')
  const name = item?.querySelector('.pm-name')?.textContent?.trim()
  return name || null
}

function messageNode(button: HTMLButtonElement): HTMLDivElement | null {
  const item = button.closest('.pm-item')
  if (!item) return null
  let node = item.querySelector('.pm-update-enhanced') as HTMLDivElement | null
  if (!node) {
    node = document.createElement('div')
    node.className = 'pm-update-msg pm-update-enhanced'
    const desc = item.querySelector('.pm-item-desc')
    desc?.insertAdjacentElement('afterend', node)
  }
  return node
}

function setMessage(button: HTMLButtonElement, type: 'success' | 'error' | 'info', message: string): void {
  const node = messageNode(button)
  if (!node) return
  node.textContent = message
  node.classList.remove('pm-update-error', 'pm-update-success', 'pm-update-info')
  node.classList.add(type === 'error' ? 'pm-update-error' : type === 'success' ? 'pm-update-success' : 'pm-update-info')
}

function setBusy(button: HTMLButtonElement, busy: boolean): void {
  button.disabled = busy
  button.classList.toggle('pm-btn-updating', busy)
  button.setAttribute('aria-busy', String(busy))
  const icon = button.querySelector('svg')
  icon?.classList.toggle('pm-spin', busy)
}

async function fetchServices(): Promise<ServiceInfo[]> {
  const response = await fetch(`${CONTROL_API}/services`, { cache: 'no-store' })
  if (!response.ok) throw new Error('Unable to read service update status')
  const data = await readJson<{ services?: ServiceInfo[] }>(response)
  return data.services || []
}

async function pollServiceUpdate(serviceName: string, onProgress: (message: string) => void): Promise<ServiceInfo | null> {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    await sleep(2000)
    try {
      const services = await fetchServices()
      const service = services.find(item => item.name === serviceName)
      if (!service) continue
      if (service.update_in_progress) {
        onProgress(`Updating ${serviceName}…`)
        continue
      }
      if (service.last_update) return service
      return service
    } catch {
      onProgress(`Waiting for ${serviceName} update status…`)
    }
  }
  return null
}

async function updateLatest(serviceName: string, button: HTMLButtonElement): Promise<void> {
  setBusy(button, true)
  setMessage(button, 'info', `Starting ${serviceName} update…`)
  try {
    const response = await fetch(`${CONTROL_API}/v2/services/${encodeURIComponent(serviceName)}/update-latest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ restart: true }),
    })
    const data = await readJson<UpdateResponse>(response)
    if (!response.ok || data.ok === false) {
      throw new Error(parseErrorPayload(data, `${serviceName} update failed`))
    }

    if (data.deferred) {
      setMessage(button, 'info', data.message || `${serviceName} update is running in the background…`)
      const service = await pollServiceUpdate(serviceName, message => setMessage(button, 'info', message))
      const update = service?.last_update
      if (!update) {
        setMessage(button, 'info', `${serviceName} update is still running. Refresh services for final status.`)
        return
      }
      if (update.status === 'failed') {
        setMessage(button, 'error', update.error?.message || update.message || `${serviceName} update failed`)
        return
      }
      const suffix = update.commit ? ` (${update.commit.slice(0, 7)})` : ''
      setMessage(button, 'success', update.message || `${serviceName} updated${suffix}`)
      return
    }

    setMessage(button, 'success', data.message || `${serviceName} updated`)
  } catch (error) {
    setMessage(button, 'error', error instanceof Error ? error.message : `${serviceName} update failed`)
  } finally {
    setBusy(button, false)
  }
}

function handleClick(event: MouseEvent): void {
  const button = findUpdateButton(event.target)
  if (!button || button.disabled) return
  const serviceName = findServiceName(button)
  if (!serviceName) return
  event.preventDefault()
  event.stopPropagation()
  event.stopImmediatePropagation()
  void updateLatest(serviceName, button)
}

document.addEventListener('click', handleClick, true)
