import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './server-app-panel'
import './styles.css'
import './service-update-enhancer.css'
import './no-placeholder-actions.css'
import './ux-polish.css'
import './server-app-launcher.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>
)
