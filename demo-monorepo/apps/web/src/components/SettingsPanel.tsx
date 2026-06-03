import React, { useState, useEffect } from 'react'

interface Settings {
  theme: 'light' | 'dark'
  notifications: boolean
  autoSave: boolean
}

export function SettingsPanel() {
  const [settings, setSettings] = useState<Settings>({
    theme: 'light',
    notifications: true,
    autoSave: false,
  })
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    fetch('/api/settings').then(r => r.json()).then(setSettings).catch(() => {})
  }, [])

  async function save() {
    await fetch('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    })
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div style={{ padding: 16, border: '1px solid #ddd', borderRadius: 8 }}>
      <h3>Settings</h3>
      <div style={{ marginBottom: 12 }}>
        <label>
          Theme:
          <select value={settings.theme} onChange={e => setSettings(s => ({ ...s, theme: e.target.value as 'light' | 'dark' }))}>
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </select>
        </label>
      </div>
      <div style={{ marginBottom: 12 }}>
        <label>
          <input type="checkbox" checked={settings.notifications} onChange={e => setSettings(s => ({ ...s, notifications: e.target.checked }))} />
          Enable notifications
        </label>
      </div>
      <div style={{ marginBottom: 12 }}>
        <label>
          <input type="checkbox" checked={settings.autoSave} onChange={e => setSettings(s => ({ ...s, autoSave: e.target.checked }))} />
          Auto-save tasks
        </label>
      </div>
      <button onClick={save}>Save Settings</button>
      {saved && <span style={{ marginLeft: 8, color: 'green' }}>Saved!</span>}
    </div>
  )
}
