import React, { useState, useEffect } from 'react'
import { TaskList } from './components/TaskList'
import { TaskForm } from './components/TaskForm'
import { SettingsPanel } from './components/SettingsPanel'
import { type Task } from '@taskflow/shared'

export function App() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [page, setPage] = useState<'tasks' | 'settings'>('tasks')
  const [error, setError] = useState('')

  useEffect(() => { fetchTasks() }, [])

  async function fetchTasks() {
    try {
      const res = await fetch('/api/tasks')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setTasks(await res.json())
    } catch (e: any) {
      setError(e.message)
    }
  }

  async function createTask(title: string, description: string) {
    const res = await fetch('/api/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, description }),
    })
    if (!res.ok) throw new Error('Failed to create task')
    await fetchTasks()
  }

  async function toggleTask(id: string) {
    const task = tasks.find(t => t.id === id)
    if (!task) return
    await fetch(`/api/tasks/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ completed: !task.completed }),
    })
    await fetchTasks()
  }

  async function deleteTask(id: string) {
    await fetch(`/api/tasks/${id}`, { method: 'DELETE' })
    await fetchTasks()
  }

  return (
    <div style={{ maxWidth: 800, margin: '0 auto', padding: 20 }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h1>TaskFlow</h1>
        <nav>
          <button onClick={() => setPage('tasks')} disabled={page === 'tasks'}>Tasks</button>
          <button onClick={() => setPage('settings')} disabled={page === 'settings'}>Settings</button>
        </nav>
      </header>
      {error && <div style={{ color: 'red', marginBottom: 10 }}>Error: {error}</div>}
      {page === 'tasks' ? (
        <>
          <TaskForm onSubmit={createTask} />
          <TaskList tasks={tasks} onToggle={toggleTask} onDelete={deleteTask} />
        </>
      ) : (
        <SettingsPanel />
      )}
    </div>
  )
}
