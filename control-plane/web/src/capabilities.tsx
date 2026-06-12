import { useEffect, useMemo, useState, type ReactNode } from 'react'

export type CapabilityVisibility = 'render' | 'disabled' | 'omit'

export interface UiCapability {
  key: string
  label: string
  area: string
  enabled: boolean
  visibility: CapabilityVisibility
  reason: string
  endpoints: string[]
  routes: string[]
  local_actions: string[]
  external_targets: string[]
  intent: string
}

export interface UiCapabilitiesResponse {
  version: number
  intent: string
  capabilities: UiCapability[]
}

export type CapabilityMap = Record<string, UiCapability>

const CONTROL_API = window.location.port === '5173'
  ? `${window.location.protocol}//${window.location.hostname}:9877/api`
  : '/api'

function endpoint(path: string): string {
  return `${CONTROL_API}${path.startsWith('/') ? path : `/${path}`}`
}

export function buildCapabilityMap(capabilities: UiCapability[]): CapabilityMap {
  return capabilities.reduce<CapabilityMap>((acc, capability) => {
    acc[capability.key] = capability
    return acc
  }, {})
}

export function isCapabilityRenderable(capability?: UiCapability): boolean {
  if (!capability) return false
  return capability.enabled && capability.visibility === 'render'
}

export function isCapabilityDisabled(capability?: UiCapability): boolean {
  if (!capability) return true
  return !capability.enabled || capability.visibility === 'disabled'
}

export function useUiCapabilities() {
  const [capabilities, setCapabilities] = useState<UiCapability[]>([])
  const [intent, setIntent] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError('')
      try {
        const response = await fetch(endpoint('/ui/capabilities'))
        if (!response.ok) throw new Error(await response.text() || `${response.status} ${response.statusText}`)
        const data = await response.json() as UiCapabilitiesResponse
        if (cancelled) return
        setCapabilities(data.capabilities || [])
        setIntent(data.intent || '')
      } catch (err) {
        if (!cancelled) setError((err as Error).message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  const byKey = useMemo(() => buildCapabilityMap(capabilities), [capabilities])

  return { capabilities, byKey, intent, loading, error }
}

export function FeatureGate({
  capability,
  children,
  fallback = null,
}: {
  capability?: UiCapability
  children: ReactNode
  fallback?: ReactNode
}) {
  if (!isCapabilityRenderable(capability)) return <>{fallback}</>
  return <>{children}</>
}

export function CapabilityButton({
  capability,
  children,
  disabled,
  title,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  capability?: UiCapability
}) {
  if (!capability || capability.visibility === 'omit') return null
  const capabilityDisabled = isCapabilityDisabled(capability)
  return (
    <button
      {...props}
      disabled={disabled || capabilityDisabled}
      title={title || (capabilityDisabled ? capability.reason : capability.intent)}
    >
      {children}
    </button>
  )
}
