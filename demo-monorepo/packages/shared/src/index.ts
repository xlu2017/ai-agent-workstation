export interface Task {
  id: string
  title: string
  description: string
  completed: boolean
  createdAt: string
  updatedAt: string
}

export interface ValidationResult {
  valid: boolean
  errors: string[]
}

export function validateTask(data: { title?: string; description?: string }): ValidationResult {
  const errors: string[] = []

  if (!data.title || data.title.trim().length === 0) {
    errors.push('Title is required')
  } else if (data.title.length > 200) {
    errors.push('Title must be 200 characters or less')
  }

  if (data.description && data.description.length > 2000) {
    errors.push('Description must be 2000 characters or less')
  }

  return { valid: errors.length === 0, errors }
}

export function generateId(): string {
  return `task-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}
