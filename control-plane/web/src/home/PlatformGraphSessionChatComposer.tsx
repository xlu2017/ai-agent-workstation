import { ArrowUp } from 'lucide-react'

export default function PlatformGraphSessionChatComposer({
  value,
  disabled,
  onChange,
  onSubmit,
}: {
  value: string
  disabled?: boolean
  onChange: (value: string) => void
  onSubmit: () => void
}) {
  return (
    <div className="workspace-chat-composer">
      <textarea
        value={value}
        onChange={event => onChange(event.target.value)}
        onKeyDown={event => {
          if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault()
            onSubmit()
          }
        }}
        placeholder="Continue this session..."
        rows={3}
      />
      <button type="button" disabled={disabled || !value.trim()} onClick={onSubmit} aria-label="Send message">
        <ArrowUp size={18} />
      </button>
    </div>
  )
}
