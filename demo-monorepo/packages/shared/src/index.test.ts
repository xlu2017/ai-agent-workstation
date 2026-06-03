import { describe, it, expect } from 'vitest'
import { validateTask, generateId } from './index'

describe('validateTask', () => {
  it('requires title', () => {
    const result = validateTask({ title: '' })
    expect(result.valid).toBe(false)
    expect(result.errors).toContain('Title is required')
  })

  it('rejects long title', () => {
    const result = validateTask({ title: 'a'.repeat(201) })
    expect(result.valid).toBe(false)
    expect(result.errors).toContain('Title must be 200 characters or less')
  })

  it('rejects long description', () => {
    const result = validateTask({ title: 'ok', description: 'a'.repeat(2001) })
    expect(result.valid).toBe(false)
  })

  it('accepts valid input', () => {
    const result = validateTask({ title: 'My task', description: 'Details' })
    expect(result.valid).toBe(true)
    expect(result.errors).toHaveLength(0)
  })
})

describe('generateId', () => {
  it('returns unique IDs', () => {
    const a = generateId()
    const b = generateId()
    expect(a).not.toBe(b)
    expect(a).toMatch(/^task-/)
  })
})
