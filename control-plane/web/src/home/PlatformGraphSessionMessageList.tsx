import type { ChatTurn } from './types'

export default function PlatformGraphSessionMessageList({ turns }: { turns: ChatTurn[] }) {
  if (!turns.length) {
    return <div className="workspace-empty-message">No chat turns recorded yet.</div>
  }

  return (
    <div className="workspace-message-list">
      {turns.map((turn, index) => (
        <article key={`${turn.role}-${index}-${turn.created_at || ''}`} className={`workspace-message ${turn.role}`}>
          <span>{turn.role}</span>
          <p>{turn.content}</p>
        </article>
      ))}
    </div>
  )
}
