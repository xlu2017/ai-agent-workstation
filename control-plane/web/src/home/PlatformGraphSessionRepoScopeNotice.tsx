import { GitBranch } from 'lucide-react'
import type { GraphSession } from './types'

export default function PlatformGraphSessionRepoScopeNotice({ session }: { session: GraphSession }) {
  const hasRepo = Boolean(session.metadata?.repo_attached_at_start || session.metadata?.repo_session_id)

  return (
    <div className={`workspace-repo-status ${hasRepo ? 'attached' : 'missing'}`}>
      <GitBranch size={16} />
      <div>
        <strong>{hasRepo ? 'Repo context attached' : 'Repo context not selected'}</strong>
        <p>{hasRepo ? 'This goal has mounted repo context.' : 'Choose repo context before code execution.'}</p>
      </div>
    </div>
  )
}
