import { Router } from 'express'
import { validateTask } from '@taskflow/shared'
import { db } from '@taskflow/db'

export const taskRoutes = Router()

taskRoutes.get('/', (_req, res) => {
  const tasks = db.getAllTasks()
  res.json(tasks)
})

taskRoutes.post('/', (req, res) => {
  const { title, description } = req.body
  const validation = validateTask({ title, description })
  if (!validation.valid) {
    res.status(400).json({ error: validation.errors })
    return
  }
  const task = db.createTask({ title, description })
  res.status(201).json(task)
})

taskRoutes.patch('/:id', (req, res) => {
  const { id } = req.params
  const task = db.getTask(id)
  if (!task) {
    res.status(404).json({ error: 'Task not found' })
    return
  }
  const updated = db.updateTask(id, req.body)
  res.json(updated)
})

taskRoutes.delete('/:id', (req, res) => {
  const { id } = req.params
  const task = db.getTask(id)
  if (!task) {
    res.status(404).json({ error: 'Task not found' })
    return
  }
  db.deleteTask(id)
  res.status(204).send()
})
