import { useCallback, useEffect, useState } from 'react'
import App from './App'
import PlatformHomeInitialChatScreen from './home/PlatformHomeInitialChatScreen'
import PlatformGraphSessionWorkspaceScreen from './home/PlatformGraphSessionWorkspaceScreen'
import './platform-home.css'

export default function PlatformHome() {
  const [path, setPath] = useState(window.location.pathname)

  const go = useCallback((nextPath: string) => {
    window.history.pushState({}, '', nextPath)
    setPath(nextPath)
  }, [])

  useEffect(() => {
    const onPopState = () => setPath(window.location.pathname)
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  if (path === '/') return <PlatformHomeInitialChatScreen onNavigate={go} />
  if (path.startsWith('/session/')) return <PlatformGraphSessionWorkspaceScreen sessionId={path.replace('/session/', '')} onNavigate={go} />
  return <App />
}
