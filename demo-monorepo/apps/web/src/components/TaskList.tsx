import React from 'react'
import { type Task } from '@taskflow/shared'

interface TaskListProps {
  tasks: Task[]
  onToggle: (id: string) => void
  onDelete: (id: string) => void
}

export function TaskList({ tasks, onToggle, onDelete }: TaskListProps) {
  if (tasks.length === 0) return <p>No tasks yet. Create one above!</p>

  return (
    <ul style={{ listStyle: 'none', padding: 0 }}>
      {tasks.map(task => (
        <li key={task.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0', borderBottom: '1px solid #eee' }}>
          <input
            type="checkbox"
            checked={task.completed}
            onChange={() => onToggle(task.id)}
          />
          <div style={{ flex: 1 }}>
            <strong style={{ textDecoration: task.completed ? 'line-through' : 'none' }}>{task.title}</strong>
            {task.description && <p style={{ margin: '4px 0 0', color: '#666', fontSize: 14 }}>{task.description}</p>}
          </div>
          <button onClick={() => onDelete(task.id)} style={{ color: 'red' }}>Delete</button>
        </li>
      ))}
    </ul>
  )
}
