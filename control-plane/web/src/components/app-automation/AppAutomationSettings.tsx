import { useCallback, useEffect, useMemo, useState } from 'react'
import { CheckCircle2, ExternalLink, RefreshCw, Settings2, ShieldAlert, X } from 'lucide-react'
import './AppAutomationSettings.css'

const CONTROL_API = window.location.port === '5173'
  ? `${window.location.protocol}//${window.location.hostname}:9877/api`
  : '/api'

function endpoint(path: string): string {
  return `${CONTROL_API}${path.startsWith('/') ? path : `/${path}`}`
}

type RuntimeKind = 'url' | 'command' | 'provider'

type RuntimeConfig = {
  vendor_id: string
  configurable: boolean
  configured: boolean
  config_source: 'environment' | 'stored' | 'provider' | 'unconfigured' | string
  env_name?: string | null
  kind: RuntimeKind | string
  label: string
  description: string
  placeholder: string
  value_preview?: string | null
  stored_enabled?: boolean
  can_edit?: boolean
}

type VendorStatus = {
  id: string
  name: string
  role: string
  target_dir: string
  installed: boolean
  local_adapter_present?: boolean
  runtime_config?: RuntimeConfig
}

type VendorsResponse = {
  vendors: VendorStatus[]
  default_execution_ladder: string[]
}

type ConfigResponse = {
  vendors: RuntimeConfig[]
  config_path?: string
  updated_at?: string | null
}

type ConfigureModalState = {
  vendor: VendorStatus
  config: RuntimeConfig
}

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(endpoint(path))
  if (!res.ok) throw new Error(await res.text() || `${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

function statusText(config?: RuntimeConfig): string {
  if (!config) return 'unknown'
  if (config.config_source === 'environment') return 'configured by environment'
  if (config.config_source === 'stored') return 'configured'
  if (config.config_source === 'provider') return 'configured through provider'
  return 'unconfigured'
}

function statusClass(config?: RuntimeConfig): string {
  if (!config) return 'neutral'
  if (['environment', 'stored', 'provider'].includes(config.config_source)) return 'ok'
  return 'warn'
}

function valueLabel(config: RuntimeConfig): string {
  if (config.kind === 'command') return 'Command'
  if (config.kind === 'url') return 'Endpoint URL'
  return 'Provider configuration'
}

export default function AppAutomationSettings() {
  const [vendors, setVendors] = useState<VendorStatus[]>([])
  const [config, setConfig] = useState<ConfigResponse>({ vendors: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [modal, setModal] = useState<ConfigureModalState | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [vendorData, configData] = await Promise.all([
        fetchJson<VendorsResponse>('/app-automation/vendors'),
        fetchJson<ConfigResponse>('/app-automation/config'),
      ])
      const configByVendor = new Map(configData.vendors.map(item => [item.vendor_id, item]))
      setVendors(vendorData.vendors.map(vendor => ({
        ...vendor,
        runtime_config: vendor.runtime_config || configByVendor.get(vendor.id),
      })))
      setConfig(configData)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const counts = useMemo(() => {
    const configurable = vendors.filter(v => v.runtime_config?.configurable).length
    const configured = vendors.filter(v => v.runtime_config?.configured || v.runtime_config?.config_source === 'provider').length
    const unconfigured = vendors.filter(v => v.runtime_config?.configurable && !v.runtime_config?.configured).length
    return { configurable, configured, unconfigured }
  }, [vendors])

  return (
    <section className="app-automation-settings-card">
      <div className="app-automation-settings-head">
        <div>
          <h3>App automation runtimes</h3>
          <p>Configure live vendor endpoints or commands when a selected automation runtime is not configured.</p>
        </div>
        <button className="settings-btn" onClick={load} disabled={loading}><RefreshCw size={14} /> Refresh</button>
      </div>

      {error && <div className="settings-error">{error}</div>}

      <div className="app-automation-summary-grid">
        <div><span>Vendors</span><strong>{vendors.length}</strong></div>
        <div><span>Configurable</span><strong>{counts.configurable}</strong></div>
        <div><span>Configured</span><strong>{counts.configured}</strong></div>
        <div><span>Needs config</span><strong>{counts.unconfigured}</strong></div>
      </div>

      {loading ? <div className="settings-empty">Loading app automation configuration…</div> : (
        <div className="app-automation-vendor-list">
          {vendors.map(vendor => {
            const runtime = vendor.runtime_config
            const needsConfig = runtime?.configurable && !runtime.configured
            return (
              <div className="app-automation-vendor-row" key={vendor.id}>
                <div className="app-automation-vendor-main">
                  <div className="app-automation-vendor-title-row">
                    <strong>{vendor.name || vendor.id}</strong>
                    <span className={`app-automation-status app-automation-status-${statusClass(runtime)}`}>{statusText(runtime)}</span>
                    {vendor.local_adapter_present && <span className="app-automation-chip"><CheckCircle2 size={12} /> local adapter</span>}
                  </div>
                  <p>{vendor.role}</p>
                  <small>{runtime?.description || vendor.target_dir}</small>
                </div>
                <div className="app-automation-vendor-actions">
                  {runtime?.value_preview && <code>{runtime.value_preview}</code>}
                  {runtime?.config_source === 'environment' && <span className="app-automation-readonly">{runtime.env_name}</span>}
                  {runtime?.config_source === 'provider' && <span className="app-automation-readonly">Repo Provider</span>}
                  {runtime?.can_edit && (
                    <button className={`settings-btn ${needsConfig ? 'settings-btn-primary' : ''}`} onClick={() => setModal({ vendor, config: runtime })}>
                      <Settings2 size={14} /> {needsConfig ? 'Configure' : 'Update'}
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      <div className="app-automation-note">
        <ShieldAlert size={14} /> Environment variables still override values saved here. Stored values are redacted in the UI and should point at controlled internal endpoints or commands.
      </div>

      {config.config_path && <p className="app-automation-config-path">Saved server-side at <code>{config.config_path}</code></p>}

      {modal && <ConfigureVendorModal modal={modal} onClose={() => setModal(null)} onSaved={() => { setModal(null); load() }} />}
    </section>
  )
}

function ConfigureVendorModal({ modal, onClose, onSaved }: { modal: ConfigureModalState; onClose: () => void; onSaved: () => void }) {
  const [value, setValue] = useState('')
  const [enabled, setEnabled] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const label = valueLabel(modal.config)

  useEffect(() => {
    const listener = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    document.addEventListener('keydown', listener)
    return () => document.removeEventListener('keydown', listener)
  }, [onClose])

  const save = async () => {
    setSaving(true)
    setError('')
    try {
      const res = await fetch(endpoint(`/app-automation/config/${modal.config.vendor_id}`), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value, enabled }),
      })
      if (!res.ok) throw new Error(await res.text() || `${res.status} ${res.statusText}`)
      onSaved()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const clear = async () => {
    setSaving(true)
    setError('')
    try {
      const res = await fetch(endpoint(`/app-automation/config/${modal.config.vendor_id}`), { method: 'DELETE' })
      if (!res.ok) throw new Error(await res.text() || `${res.status} ${res.statusText}`)
      onSaved()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="app-automation-modal-backdrop" role="presentation" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="app-automation-modal" role="dialog" aria-modal="true" aria-labelledby="app-automation-modal-title">
        <div className="app-automation-modal-head">
          <div>
            <h3 id="app-automation-modal-title">Configure {modal.vendor.name || modal.vendor.id}</h3>
            <p>{modal.config.description}</p>
          </div>
          <button className="app-automation-icon-btn" onClick={onClose} aria-label="Close"><X size={16} /></button>
        </div>

        <label className="app-automation-field">
          <span>{label}</span>
          <input value={value} onChange={e => setValue(e.target.value)} placeholder={modal.config.placeholder} autoFocus />
          <small>{modal.config.kind === 'command' ? 'The command runs from the vendored source directory and receives the JSON action envelope on stdin.' : 'Use a controlled internal endpoint that accepts the normalized action envelope.'}</small>
        </label>

        <label className="app-automation-checkbox-row">
          <input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} />
          <span>Enable this runtime configuration</span>
        </label>

        {modal.config.env_name && <div className="app-automation-env-note"><ExternalLink size={13} /> Server environment override: <code>{modal.config.env_name}</code></div>}
        {modal.config.value_preview && <div className="app-automation-env-note">Current stored/environment value: <code>{modal.config.value_preview}</code>. Enter a new value to replace stored configuration.</div>}
        {error && <div className="settings-error">{error}</div>}

        <div className="app-automation-modal-actions">
          {modal.config.config_source === 'stored' && <button className="settings-btn" onClick={clear} disabled={saving}>Clear saved config</button>}
          <span className="app-automation-modal-spacer" />
          <button className="settings-btn" onClick={onClose} disabled={saving}>Cancel</button>
          <button className="settings-btn settings-btn-primary" onClick={save} disabled={saving || (enabled && !value.trim())}>{saving ? 'Saving…' : 'Save configuration'}</button>
        </div>
      </div>
    </div>
  )
}
