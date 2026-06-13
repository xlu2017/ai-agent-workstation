import { useCallback, useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Settings2, X } from 'lucide-react'
import './components/app-automation/AppAutomationSettings.css'

const CONTROL_API = window.location.port === '5173'
  ? `${window.location.protocol}//${window.location.hostname}:9877/api`
  : '/api'

function endpoint(path: string): string {
  return `${CONTROL_API}${path.startsWith('/') ? path : `/${path}`}`
}

type RuntimeConfig = {
  vendor_id: string
  configurable: boolean
  configured: boolean
  config_source: string
  env_name?: string | null
  kind: 'url' | 'command' | 'provider' | string
  label: string
  description: string
  placeholder: string
  value_preview?: string | null
  can_edit?: boolean
}

type ConfigResponse = { vendors: RuntimeConfig[] }

type ConfigureEventDetail = { vendor?: string; vendor_id?: string; reason?: string }

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(endpoint(path))
  if (!res.ok) throw new Error(await res.text() || `${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

function needsConfig(vendor: RuntimeConfig): boolean {
  return Boolean(vendor.configurable && !vendor.configured && vendor.config_source === 'unconfigured')
}

function valueLabel(vendor: RuntimeConfig): string {
  if (vendor.kind === 'command') return 'Command'
  if (vendor.kind === 'url') return 'Endpoint URL'
  return 'Provider configuration'
}

function installFetchInterceptor() {
  const key = '__jubilantAppAutomationFetchInterceptorInstalled'
  if ((window as any)[key]) return
  ;(window as any)[key] = true
  const originalFetch = window.fetch.bind(window)
  window.fetch = async (...args: Parameters<typeof fetch>): Promise<Response> => {
    const response = await originalFetch(...args)
    try {
      const input = args[0]
      const url = typeof input === 'string' ? input : input instanceof Request ? input.url : input instanceof URL ? input.toString() : ''
      if (url.includes('/app-automation/execute')) {
        response.clone().json().then((body: any) => {
          if (body?.status === 'runtime_not_configured' || body?.error?.code === 'RUNTIME_NOT_CONFIGURED') {
            window.dispatchEvent(new CustomEvent<ConfigureEventDetail>('app-automation:configure', { detail: { vendor: body.vendor, reason: body.message } }))
          }
        }).catch(() => undefined)
      }
    } catch {
      // Preserve original fetch behavior even if the helper cannot parse a response.
    }
    return response
  }
}

function AppAutomationConfigPopup() {
  const [configs, setConfigs] = useState<RuntimeConfig[]>([])
  const [open, setOpen] = useState(false)
  const [selectedVendorId, setSelectedVendorId] = useState<string | null>(null)
  const [value, setValue] = useState('')
  const [enabled, setEnabled] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    try {
      const data = await fetchJson<ConfigResponse>('/app-automation/config')
      setConfigs(data.vendors || [])
    } catch (err) {
      setError((err as Error).message)
    }
  }, [])

  useEffect(() => { installFetchInterceptor(); load() }, [load])

  useEffect(() => {
    const listener = (event: Event) => {
      const detail = (event as CustomEvent<ConfigureEventDetail>).detail || {}
      const vendorId = detail.vendor_id || detail.vendor
      setNotice(detail.reason || '')
      setSelectedVendorId(vendorId || null)
      setValue('')
      setEnabled(true)
      setOpen(true)
      load()
    }
    window.addEventListener('app-automation:configure', listener)
    return () => window.removeEventListener('app-automation:configure', listener)
  }, [load])

  useEffect(() => {
    if (!open) return
    const listener = (event: KeyboardEvent) => { if (event.key === 'Escape') setOpen(false) }
    document.addEventListener('keydown', listener)
    return () => document.removeEventListener('keydown', listener)
  }, [open])

  const unconfigured = useMemo(() => configs.filter(needsConfig), [configs])
  const selected = useMemo(() => {
    if (selectedVendorId) return configs.find(item => item.vendor_id === selectedVendorId) || null
    return unconfigured[0] || configs.find(item => item.configurable && item.can_edit) || null
  }, [configs, selectedVendorId, unconfigured])

  const save = async () => {
    if (!selected) return
    setSaving(true)
    setError('')
    try {
      const res = await fetch(endpoint(`/app-automation/config/${selected.vendor_id}`), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value, enabled }),
      })
      if (!res.ok) throw new Error(await res.text() || `${res.status} ${res.statusText}`)
      setValue('')
      await load()
      setOpen(false)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const clear = async () => {
    if (!selected) return
    setSaving(true)
    setError('')
    try {
      const res = await fetch(endpoint(`/app-automation/config/${selected.vendor_id}`), { method: 'DELETE' })
      if (!res.ok) throw new Error(await res.text() || `${res.status} ${res.statusText}`)
      await load()
      setOpen(false)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  if (!open && !unconfigured.length) return null

  return (
    <>
      {!open && unconfigured.length > 0 && (
        <button className="app-automation-floating-config" onClick={() => { setOpen(true); setSelectedVendorId(unconfigured[0]?.vendor_id || null) }}>
          <Settings2 size={14} /> Configure app automation ({unconfigured.length})
        </button>
      )}

      {open && (
        <div className="app-automation-modal-backdrop" role="presentation" onMouseDown={e => { if (e.target === e.currentTarget) setOpen(false) }}>
          <div className="app-automation-modal" role="dialog" aria-modal="true" aria-labelledby="app-automation-config-title">
            <div className="app-automation-modal-head">
              <div>
                <h3 id="app-automation-config-title">Configure app automation</h3>
                <p>{notice || 'Enter the missing endpoint or command for an unconfigured vendor runtime.'}</p>
              </div>
              <button className="app-automation-icon-btn" onClick={() => setOpen(false)} aria-label="Close"><X size={16} /></button>
            </div>

            {configs.length > 1 && (
              <label className="app-automation-field">
                <span>Vendor</span>
                <select value={selected?.vendor_id || ''} onChange={e => { setSelectedVendorId(e.target.value); setValue('') }}>
                  {configs.filter(item => item.configurable).map(item => <option key={item.vendor_id} value={item.vendor_id}>{item.label} — {item.config_source}</option>)}
                </select>
              </label>
            )}

            {selected ? (
              <>
                <label className="app-automation-field">
                  <span>{valueLabel(selected)}</span>
                  <input value={value} onChange={e => setValue(e.target.value)} placeholder={selected.placeholder} autoFocus />
                  <small>{selected.description}</small>
                </label>
                <label className="app-automation-checkbox-row"><input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} /><span>Enable this runtime configuration</span></label>
                {selected.env_name && <div className="app-automation-env-note">Environment override: <code>{selected.env_name}</code></div>}
                {selected.value_preview && <div className="app-automation-env-note">Current value: <code>{selected.value_preview}</code>. Enter a new value to replace stored configuration.</div>}
                {error && <div className="settings-error">{error}</div>}
                <div className="app-automation-modal-actions">
                  {selected.config_source === 'stored' && <button className="settings-btn" onClick={clear} disabled={saving}>Clear saved config</button>}
                  <span className="app-automation-modal-spacer" />
                  <button className="settings-btn" onClick={() => setOpen(false)} disabled={saving}>Cancel</button>
                  <button className="settings-btn settings-btn-primary" onClick={save} disabled={saving || (enabled && !value.trim())}>{saving ? 'Saving…' : 'Save configuration'}</button>
                </div>
              </>
            ) : <div className="settings-empty">No configurable app automation vendor was returned.</div>}
          </div>
        </div>
      )}
    </>
  )
}

const mount = document.createElement('div')
mount.id = 'app-automation-config-popup-root'
document.body.appendChild(mount)
createRoot(mount).render(<AppAutomationConfigPopup />)
