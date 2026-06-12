import { useCallback, useEffect, useState } from 'react'
import App from '../App'
import PlatformHome from '../PlatformHome'

export default function PlatformHomeRouteShell() {
  const [routePath, setRoutePath] = useState(window.location.pathname)

  const navigate = useCallback((path: string) => {
    window.history.pushState({}, '', path)
    setRoutePath(path)
  }, [])

  useEffect(() => {
    const handler = () => setRoutePath(window.location.pathname)
    window.addEventListener('popstate', handler)
    return () => window.removeEventListener('popstate', handler)
  }, [])

  if (routePath === '/' || routePath.startsWith('/session/')) {
    return <PlatformHome />
  }

  return <App />
}
