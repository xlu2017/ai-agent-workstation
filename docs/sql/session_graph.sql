CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  summary TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'proposed',
  parent_id TEXT NULL REFERENCES sessions(id),
  root_id TEXT NULL REFERENCES sessions(id),
  facets JSONB NOT NULL DEFAULT '{}',
  policy JSONB NOT NULL DEFAULT '{}',
  state JSONB NOT NULL DEFAULT '{}',
  metadata JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_from_event_id TEXT NULL
);

CREATE TABLE IF NOT EXISTS session_edges (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  source_session_id TEXT NOT NULL REFERENCES sessions(id),
  target_session_id TEXT NOT NULL REFERENCES sessions(id),
  metadata JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_from_event_id TEXT NULL,
  UNIQUE (type, source_session_id, target_session_id)
);

CREATE TABLE IF NOT EXISTS session_events (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  session_id TEXT NOT NULL,
  root_session_id TEXT NULL,
  actor TEXT NOT NULL DEFAULT 'system',
  data JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS session_artifacts (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(id),
  artifact_type TEXT NOT NULL,
  uri TEXT NOT NULL,
  mime_type TEXT NULL,
  size_bytes BIGINT NULL,
  metadata JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS session_locks (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(id),
  lock_type TEXT NOT NULL,
  owner TEXT NOT NULL,
  expires_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS session_context_projections (
  id TEXT PRIMARY KEY,
  active_session_id TEXT NOT NULL REFERENCES sessions(id),
  source_session_ids TEXT[] NOT NULL,
  projection_mode TEXT NOT NULL,
  projection_source TEXT NOT NULL DEFAULT 'heuristic',
  relevance_score NUMERIC NOT NULL DEFAULT 0.5,
  evidence JSONB NOT NULL DEFAULT '[]',
  include_selectors JSONB NOT NULL DEFAULT '[]',
  exclude_selectors JSONB NOT NULL DEFAULT '[]',
  budget JSONB NOT NULL DEFAULT '{}',
  rationale TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS session_adapter_mappings (
  id TEXT PRIMARY KEY,
  adaptation_session_id TEXT NOT NULL REFERENCES sessions(id),
  source JSONB NOT NULL,
  target JSONB NOT NULL,
  relationship TEXT NOT NULL,
  confidence NUMERIC NOT NULL,
  evidence JSONB NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'hypothesis',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS session_memory_chunks (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(id),
  content TEXT NOT NULL,
  embedding vector(1536),
  metadata JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sessions_kind ON sessions(kind);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_sessions_root ON sessions(root_id);
CREATE INDEX IF NOT EXISTS idx_sessions_facets_gin ON sessions USING GIN (facets);
CREATE INDEX IF NOT EXISTS idx_sessions_policy_gin ON sessions USING GIN (policy);
CREATE INDEX IF NOT EXISTS idx_session_edges_source ON session_edges(source_session_id);
CREATE INDEX IF NOT EXISTS idx_session_edges_target ON session_edges(target_session_id);
CREATE INDEX IF NOT EXISTS idx_session_edges_type ON session_edges(type);
CREATE INDEX IF NOT EXISTS idx_session_events_session ON session_events(session_id);
CREATE INDEX IF NOT EXISTS idx_session_events_root ON session_events(root_session_id);
CREATE INDEX IF NOT EXISTS idx_session_events_type ON session_events(type);
CREATE INDEX IF NOT EXISTS idx_session_context_projections_active ON session_context_projections(active_session_id);
CREATE INDEX IF NOT EXISTS idx_session_adapter_mappings_adapter ON session_adapter_mappings(adaptation_session_id);
CREATE INDEX IF NOT EXISTS idx_session_memory_chunks_session ON session_memory_chunks(session_id);
