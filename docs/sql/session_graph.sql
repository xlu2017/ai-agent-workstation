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
  created_from_event_id TEXT NULL
);

CREATE TABLE IF NOT EXISTS session_events (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  session_id TEXT NOT NULL,
  data JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS session_artifacts (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(id),
  artifact_type TEXT NOT NULL,
  uri TEXT NOT NULL,
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

CREATE INDEX IF NOT EXISTS idx_session_edges_source ON session_edges(source_session_id);
CREATE INDEX IF NOT EXISTS idx_session_edges_target ON session_edges(target_session_id);
CREATE INDEX IF NOT EXISTS idx_session_events_session ON session_events(session_id);
CREATE INDEX IF NOT EXISTS idx_session_context_projections_active ON session_context_projections(active_session_id);
CREATE INDEX IF NOT EXISTS idx_session_adapter_mappings_adapter ON session_adapter_mappings(adaptation_session_id);
CREATE INDEX IF NOT EXISTS idx_session_memory_chunks_session ON session_memory_chunks(session_id);
