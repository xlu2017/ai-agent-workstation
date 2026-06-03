import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { TaskForm } from './TaskForm'

describe('TaskForm', () => {
  it('shows error when submitting empty title', async () => {
    const onSubmit = vi.fn()
    render(<TaskForm onSubmit={onSubmit} />)
    fireEvent.click(screen.getByText('Create Task'))
    expect(screen.getByText('Title is required')).toBeTruthy()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('calls onSubmit with title and description', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(<TaskForm onSubmit={onSubmit} />)
    fireEvent.change(screen.getByPlaceholderText('Task title'), { target: { value: 'Test task' } })
    fireEvent.change(screen.getByPlaceholderText('Description (optional)'), { target: { value: 'A description' } })
    fireEvent.click(screen.getByText('Create Task'))
    expect(onSubmit).toHaveBeenCalledWith('Test task', 'A description')
  })

  it('disables button while saving', async () => {
    const onSubmit = vi.fn().mockImplementation(() => new Promise(() => {}))
    render(<TaskForm onSubmit={onSubmit} />)
    fireEvent.change(screen.getByPlaceholderText('Task title'), { target: { value: 'Test' } })
    fireEvent.click(screen.getByText('Create Task'))
    expect(screen.getByText('Saving...')).toBeTruthy()
  })
})
