const CONTROL_PLANE_API_BASE = window.location.port === '5173'
  ? `${window.location.protocol}//${window.location.hostname}:9877/api`
  : '/api'

export function controlPlaneApiUrl(path: string): string {
  return `${CONTROL_PLANE_API_BASE}${path.startsWith('/') ? path : `/${path}`}`
}

async function readJsonOrThrow<T>(response: Response): Promise<T> {
  const text = await response.text()
  const data = text ? JSON.parse(text) : {}
  if (!response.ok) {
    const message = data?.error?.message || data?.detail || text || `${response.status} ${response.statusText}`
    throw new Error(message)
  }
  return data as T
}

export async function getControlPlaneJson<T>(path: string): Promise<T> {
  return readJsonOrThrow<T>(await fetch(controlPlaneApiUrl(path), { cache: 'no-store' }))
}

export async function postControlPlaneJson<T>(path: string, body: unknown): Promise<T> {
  return readJsonOrThrow<T>(await fetch(controlPlaneApiUrl(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }))
}

export async function patchControlPlaneJson<T>(path: string, body: unknown): Promise<T> {
  return readJsonOrThrow<T>(await fetch(controlPlaneApiUrl(path), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }))
}
