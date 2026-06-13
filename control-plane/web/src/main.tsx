import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import PlatformHome from './PlatformHome'
import './server-app-panel'
import './repo-provider-panel'
import './service-update-enhancer'
import './app-automation-config-popup'
import './capability-dom-guard'
import './styles.css'
import './service-update-enhancer.css'
import './repo-provider-panel.css'
import './ux-polish.css'
import './server-app-launcher.css'
import './multi-frontend-panel.css'
import './multi-frontend-panel'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <PlatformHome />
  </StrictMode>
)
