import type { ChatRole, ChatTurn } from './types'
import { currentIsoTimestamp } from './platformHomeRepositoryNameHelpers'

export function normalizeChatTurns(value: unknown): ChatTurn[] {
  if (!Array.isArray(value)) return []
  return value
    .filter(item => item && typeof item === 'object')
    .map(item => item as Record<string, unknown>)
    .filter(item => item.role === 'user' || item.role === 'assistant' || item.role === 'system')
    .map(item => ({
      role: item.role as ChatRole,
      content: String(item.content || ''),
      created_at: typeof item.created_at === 'string' ? item.created_at : undefined,
    }))
    .filter(item => item.content.trim())
}

export function appendChatTurn(turns: ChatTurn[], role: ChatRole, content: string): ChatTurn[] {
  const trimmed = content.trim()
  if (!trimmed) return turns
  return [...turns, { role, content: trimmed, created_at: currentIsoTimestamp() }]
}

export function assistantAcknowledgementForPrompt(prompt: string, repoAttached: boolean): string {
  const scope = repoAttached
    ? 'Repository context is attached to this graph session.'
    : 'This session is unscoped; attach a repository before code execution.'
  return `Session created. ${scope} Next, the execution bridge should turn this prompt into a work session: ${prompt}`
}
