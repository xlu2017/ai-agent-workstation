import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './service-update-enhancer'
import './styles.css'
import './service-update-enhancer.css'
import './no-placeholder-actions.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>
)
