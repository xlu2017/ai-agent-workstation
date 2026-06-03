import express from 'express'
import { taskRoutes } from './routes/tasks'
import { settingsRoutes } from './routes/settings'
import { authMiddleware } from './middleware/auth'

const app = express()
const PORT = parseInt(process.env.PORT || '3001')

app.use(express.json())
app.use(authMiddleware)
app.use('/api/tasks', taskRoutes)
app.use('/api/settings', settingsRoutes)

app.get('/api/health', (_req, res) => {
  res.json({ status: 'ok', uptime: process.uptime() })
})

app.listen(PORT, () => {
  console.log(`TaskFlow API running on port ${PORT}`)
})

export { app }
