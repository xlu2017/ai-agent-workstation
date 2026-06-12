import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle, Play, RefreshCw, Save, ShieldCheck } from 'lucide-react'
import type { GraphSnapshot, SessionView } from './sessionGraphTypes'
import { sessionTitle } from './sessionGraphTypes'

interface AutomationSettings {
  auto_apply_patch: boolean
  auto_run_tests: boolean
  auto_run_lint: boolean
  auto_run_typecheck: boolean
  auto_commit: boolean
  auto_push: boolean
  auto_create_pr: boolean
  auto_merge_pr: boolean
  auto_deploy: boolean
  auto_use_secret: boolean
  require_validation_before_external_side_effect: boolean
  require_private_session_confirmation: boolean
  certainty_thresholds: Record<string, number>
}

interface ProposedActionPreview {
  decision: string
  task_name: string
  target_session_ids: string[]
  params: Record<string, unknown>
  certainty: number
  stakes: 'read_only' | 'execution' | 'modification' | 'external_side_effect'
  risk: 'low' | 'medium' | 'high'
}

interface AuthorizationResult {
  authorized: boolean
  requires_user_confirmation: boolean
  blocked: boolean
  reason: string
  required_setting?: string | null
  warnings: string[]
}

const DEFAULT_SETTINGS: AutomationSettings = {
  auto_apply_patch: false,
  auto_run_tests: true,
  auto_run_lint: true,
  auto_run_typecheck: true,
  auto_commit: false,
  auto_push: false,
  auto_create_pr: false,
  auto_merge_pr: false,
  auto_deploy: false,
  auto_use_secret: false,
  require_validation_before_external_side_effect: true,
  require_private_session_confirmation: true,
  certainty_thresholds: {},
}

const AUTOMATION_TOGGLES: Array<{ key: keyof AutomationSettings; label: string; description: string; risk: string }> = [
  { key: 'auto_apply_patch', label: 'Auto apply patches', description: 'Allow bounded file edits after validation without asking in chat every time.', risk: 'Modification' },
  { key: 'auto_run_tests', label: 'Auto run tests', description: 'Run known test commands automatically when the next action is validated.', risk: 'Execution' },
  { key: 'auto_run_lint', label: 'Auto run lint', description: 'Run known lint commands without another chat confirmation.', risk: 'Execution' },
  { key: 'auto_run_typecheck', label: 'Auto run typecheck', description: 'Run known typecheck commands without another chat confirmation.', risk: 'Execution' },
  { key: 'auto_commit', label: 'Auto commit', description: 'Create git commits automatically after validation gates pass.', risk: 'External side effect' },
  { key: 'auto_push', label: 'Auto push', description: 'Push branches automatically after validation gates pass.', risk: 'External side effect' },
  { key: 'auto_create_pr', label: 'Auto create PR', description: 'Open pull requests automatically after validation gates pass.', risk: 'External side effect' },
  { key: 'auto_merge_pr', label: 'Auto merge PR', description: 'Merge pull requests automatically only when all hard gates pass.', risk: 'External side effect' },
  { key: 'auto_deploy', label: 'Auto deploy', description: 'Deploy automatically only when explicitly enabled and validated.', risk: 'External side effect' },
  { key: 'auto_use_secret', label: 'Auto use secrets', description: 'Allow secret-dependent actions when policy and target scope permit it.', risk: 'Sensitive' },
]

const ACTION_PRESETS: Array<{ label: string; action: Omit<ProposedActionPreview, 'target_session_ids'> }> = [
  { label: 'Run tests', action: { decision: 'execute', task_name: 'run_known_tests', params: { command: 'pnpm test', cwd: 'repo_root' }, certainty: 0.9, stakes: 'execution', risk: 'medium' } },
  { label: 'Apply patch', action: { decision: 'execute', task_name: 'apply_patch', params: { path: 'src/example.ts', patch: 'scaffold' }, certainty: 0.9, stakes: 'modification', risk: 'medium' } },
  { label: 'Commit', action: { decision: 'execute', task_name: 'commit', params: { message: 'Implement validated change' }, certainty: 0.99, stakes: 'external_side_effect', risk: 'high' } },
  { label: 'Push', action: { decision: 'execute', task_name: 'push', params: { branch: 'feature/session-work' }, certainty: 0.99, stakes: 'external_side_effect', risk: 'high' } },
]

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) } })
  const text = await response.text()
  const data = text ? JSON.parse(text) : {}
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : text || response.statusText)
  return data as T
}

function authorizationTone(result: AuthorizationResult | null): string {
  if (!result) return 'neutral'
  if (result.blocked) return 'bad'
  if (result.requires_user_confirmation) return 'warn'
  if (result.authorized) return 'ok'
  return 'neutral'
}

export default function AutomationSettingsPanel({ graph, selectedSession }: { graph: GraphSnapshot; selectedSession?: SessionView }) {
  const [settings, setSettings] = useState<AutomationSettings>(DEFAULT_SETTINGS)
  const [status, setStatus] = useState('Loading automation settings...')
  const [saving, setSaving] = useState(false)
  const [previewing, setPreviewing] = useState(false)
  const [presetIndex, setPresetIndex] = useState(0)
  const [targetSessionId, setTargetSessionId] = useState('')
  const [validationPassed, setValidationPassed] = useState(true)
  const [explicitApproval, setExplicitApproval] = useState(false)
  const [authorization, setAuthorization] = useState<AuthorizationResult | null>(null)

  const sessionMap = useMemo(() => new Map(graph.sessions.map(session => [session.id, session])), [graph.sessions])
  const preferredTarget = targetSessionId || selectedSession?.id || graph.sessions[0]?.id || ''

  const load = useCallback(() => {
    setStatus('Loading automation settings...')
    apiFetch<{ settings: Partial<AutomationSettings> }>('/api/session-graph/settings/automation')
      .then(data => { setSettings({ ...DEFAULT_SETTINGS, ...(data.settings || {}) }); setStatus('') })
      .catch(err => setStatus(`Unable to load automation settings: ${(err as Error).message}`))
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => { if (!targetSessionId && selectedSession?.id) setTargetSessionId(selectedSession.id) }, [selectedSession?.id, targetSessionId])

  const save = async () => {
    setSaving(true)
    setStatus('Saving automation settings...')
    try {
      const data = await apiFetch<{ settings: Partial<AutomationSettings> }>('/api/session-graph/settings/automation', { method: 'PUT', body: JSON.stringify(settings) })
      setSettings({ ...DEFAULT_SETTINGS, ...(data.settings || {}) })
      setStatus('Saved automation settings')
    } catch (err) {
      setStatus(`Save failed: ${(err as Error).message}`)
    } finally {
      setSaving(false)
    }
  }

  const previewAuthorization = async () => {
    setPreviewing(true)
    setAuthorization(null)
    setStatus('Previewing authorization...')
    try {
      const preset = ACTION_PRESETS[presetIndex]
      const action: ProposedActionPreview = { ...preset.action, target_session_ids: preferredTarget ? [preferredTarget] : [] }
      const data = await apiFetch<{ authorization: AuthorizationResult }>('/api/session-graph/authorization/preview', {
        method: 'POST',
        body: JSON.stringify({
          action,
          context: {
            validation_passed: validationPassed,
            explicit_user_approval: explicitApproval,
            automation_settings: settings,
          },
          graph,
        }),
      })
      setAuthorization(data.authorization)
      setStatus('Authorization preview updated')
    } catch (err) {
      setStatus(`Preview failed: ${(err as Error).message}`)
    } finally {
      setPreviewing(false)
    }
  }

  const setBool = (key: keyof AutomationSettings, value: boolean) => setSettings(previous => ({ ...previous, [key]: value }))
  const tone = authorizationTone(authorization)

  return (
    <section className="sg-card sg-automation-card">
      <div className="sg-card-header sg-card-header-split">
        <div><ShieldCheck size={16} /><h3>Action authorization</h3></div>
        <button className="sg-button" type="button" onClick={load} disabled={saving || previewing}><RefreshCw size={13} /> Reload</button>
      </div>
      <p className="sg-muted sg-small">Control whether validated actions can run automatically from session chat. Validation still happens first; these toggles only decide whether another chat confirmation is needed.</p>
      <div className="sg-automation-toggles">
        {AUTOMATION_TOGGLES.map(toggle => (
          <label key={toggle.key} className="sg-automation-toggle">
            <input type="checkbox" checked={Boolean(settings[toggle.key])} onChange={event => setBool(toggle.key, event.target.checked)} />
            <span><strong>{toggle.label}</strong><small>{toggle.description}</small></span>
            <code>{toggle.risk}</code>
          </label>
        ))}
      </div>
      <div className="sg-checkbox-row">
        <label><input type="checkbox" checked={settings.require_validation_before_external_side_effect} onChange={event => setBool('require_validation_before_external_side_effect', event.target.checked)} /> Require validation before external side effects</label>
        <label><input type="checkbox" checked={settings.require_private_session_confirmation} onChange={event => setBool('require_private_session_confirmation', event.target.checked)} /> Confirm private session actions</label>
      </div>
      <div className="sg-form-actions"><button className="sg-button sg-button-primary" type="button" onClick={save} disabled={saving}><Save size={13} /> {saving ? 'Saving...' : 'Save automation'}</button></div>

      <div className="sg-authorization-preview">
        <div className="sg-card-header"><Play size={15} /><h4>Authorization preview</h4></div>
        <div className="sg-form-grid">
          <label><span>Action</span><select value={presetIndex} onChange={event => setPresetIndex(Number(event.target.value))}>{ACTION_PRESETS.map((preset, index) => <option key={preset.label} value={index}>{preset.label}</option>)}</select></label>
          <label><span>Target session</span><select value={preferredTarget} onChange={event => setTargetSessionId(event.target.value)}><option value="">No target</option>{graph.sessions.map(session => <option key={session.id} value={session.id}>{session.title} · {session.kind}</option>)}</select></label>
        </div>
        <div className="sg-checkbox-row">
          <label><input type="checkbox" checked={validationPassed} onChange={event => setValidationPassed(event.target.checked)} /> Validation passed</label>
          <label><input type="checkbox" checked={explicitApproval} onChange={event => setExplicitApproval(event.target.checked)} /> Explicit chat approval</label>
        </div>
        <div className="sg-form-actions"><button className="sg-button" type="button" onClick={previewAuthorization} disabled={previewing || !graph.sessions.length}><Play size={13} /> {previewing ? 'Previewing...' : 'Preview authorization'}</button></div>
        {authorization && <div className={`sg-authorization-result is-${tone}`}><div>{tone === 'ok' ? <CheckCircle size={15} /> : <AlertTriangle size={15} />}<strong>{authorization.blocked ? 'Blocked' : authorization.requires_user_confirmation ? 'Confirmation required' : authorization.authorized ? 'Authorized' : 'Not authorized'}</strong></div><p>{authorization.reason}</p>{authorization.required_setting && <code>{authorization.required_setting}</code>}{authorization.warnings?.map(warning => <small key={warning}>{warning}</small>)}</div>}
        {preferredTarget && <p className="sg-muted sg-small">Preview target: {sessionTitle(sessionMap, preferredTarget)}</p>}
      </div>
      {status && <p className="sg-muted sg-small">{status}</p>}
    </section>
  )
}
