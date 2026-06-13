import { useCallback, useEffect, useState } from 'react'
import App from './App'
import PlatformHomeInitialChatScreen from './home/PlatformHomeInitialChatScreen'
import PlatformGraphSessionWorkspaceScreen from './home/PlatformGraphSessionWorkspaceScreen'
import './home/platformHomeSharedTheme.css'
import './home/platformHomeThreePaneLayout.css'
import './platform-home.css'

function normalizePath(pathname: string): string {
  return pathname === '/session' || pathname === '/session/' ? '/' : pathname
}

export default function PlatformHome() {
  const [path, setPath] = useState(() => normalizePath(window.location.pathname))

  const go = useCallback((nextPath: string) => {
    const normalized = normalizePath(nextPath)
    window.history.pushState({}, '', normalized)
    setPath(normalized)
  }, [])

  useEffect(() => {
    const normalized = normalizePath(window.location.pathname)
    if (normalized !== window.location.pathname) {
      window.history.replaceState({}, '', normalized)
      setPath(normalized)
    }

    const onPopState = () => setPath(normalizePath(window.location.pathname))
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  if (path === '/') return <PlatformHomeInitialChatScreen onNavigate={go} />
  if (path.startsWith('/session/')) {
    const sessionId = path.replace('/session/', '')
    if (!sessionId) {
      window.history.replaceState({}, '', '/')
      return <PlatformHomeInitialChatScreen onNavigate={go} />
    }
    return <PlatformGraphSessionWorkspaceScreen sessionId={sessionId} onNavigate={go} />
  }
  return <App />
}
