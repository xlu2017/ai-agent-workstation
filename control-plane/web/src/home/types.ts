export type RepoSource = 'none' | 'github' | 'local'
export type ChatRole = 'user' | 'assistant' | 'system'

export type ChatTurn = {
  role: ChatRole
  content: string
  created_at?: string
}

export type GitHubRepo = {
  id?: number
  name?: string
  full_name?: string
  description?: string | null
  private?: boolean
  default_branch?: string
  clone_url?: string
  ssh_url?: string
  html_url?: string
  updated_at?: string
}

export type BrowseEntry = {
  name: string
  path: string
  is_dir: boolean
  is_repo: boolean
}

export type GraphSession = {
  id: string
  kind: string
  title: string
  summary?: string
  status?: string
  facets?: Record<string, Record<string, unknown>>
  state?: Record<string, unknown>
  metadata?: Record<string, unknown>
  created_at?: string
  updated_at?: string
}

export type GraphSessionEvent = {
  id: string
  type: string
  session_id: string
  root_session_id?: string | null
  actor?: string
  data?: Record<string, unknown>
  created_at?: string
}

export type RepoSelection = {
  source: RepoSource
  githubRepo?: GitHubRepo
  localPath?: string
}
