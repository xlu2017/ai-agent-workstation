import { Router } from 'express'
import { db } from '@taskflow/db'

export const settingsRoutes = Router()

settingsRoutes.get('/', (_req, res) => {
  const settings = db.getSettings()
  res.json(settings)
})

settingsRoutes.put('/', (req, res) => {
  const { theme, notifications, autoSave } = req.body
  const settings = db.updateSettings({ theme, notifications, autoSave })
  res.json(settings)
})
