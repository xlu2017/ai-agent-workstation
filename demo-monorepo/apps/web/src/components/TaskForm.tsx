import React, { useState } from 'react'

interface TaskFormProps {
  onSubmit: (title: string, description: string) => Promise<void>
}

export function TaskForm({ onSubmit }: TaskFormProps) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!title.trim()) {
      setError('Title is required')
      return
    }
    setSaving(true)
    setError('')
    try {
      await onSubmit(title, description)
      setTitle('')
      setDescription('')
    } catch (err: any) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} style={{ marginBottom: 20, padding: 16, border: '1px solid #ddd', borderRadius: 8 }}>
      <h3>New Task</h3>
      {error && <div style={{ color: 'red', marginBottom: 8 }}>{error}</div>}
      <div style={{ marginBottom: 8 }}>
        <input
          type="text"
          value={title}
          onChange={e => setTitle(e.target.value)}
          placeholder="Task title"
          style={{ width: '100%', padding: 8 }}
        />
      </div>
      <div style={{ marginBottom: 8 }}>
        <textarea
          value={description}
          onChange={e => setDescription(e.target.value)}
          placeholder="Description (optional)"
          rows={3}
          style={{ width: '100%', padding: 8 }}
        />
      </div>
      <button type="submit" disabled={saving}>
        {saving ? 'Saving...' : 'Create Task'}
      </button>
    </form>
  )
}
