# RFC-007: Persistent Agent Memory

**Status:** Draft
**Author:** Infrastructure Team
**Created:** 2026-06-03

## Summary

Design a persistent memory system that allows agents to retain knowledge across sessions — project context, code patterns, past decisions, and learned preferences.

## Motivation

Current agents start fresh each session. They repeatedly:
- Re-discover project structure
- Re-learn coding patterns
- Make the same mistakes
- Ask the same questions

Persistent memory eliminates this waste and improves quality over time.

## Architecture

```
┌──────────────────────────────────────────┐
│              Memory Store                 │
│                                          │
│  ┌─────────┐  ┌──────────┐  ┌────────┐ │
│  │Episodic │  │Semantic  │  │Procedural│ │
│  │(sessions)│ │(facts)    │  │(skills) │ │
│  └─────────┘  └──────────┘  └────────┘ │
│                                          │
│  Storage: SQLite + Vector DB (ChromaDB)  │
└──────────────────┬───────────────────────┘
                   │
         ┌─────────┴──────────┐
         │  Memory Service    │  :9900
         │  (FastAPI)         │
         └─────────┬──────────┘
                   │
    ┌──────────────┼──────────────┐
    ▼              ▼              ▼
┌────────┐  ┌──────────┐  ┌──────────┐
│Agent 1 │  │ Agent 2  │  │Knowledge │
│        │  │          │  │ Loader   │
└────────┘  └──────────┘  └──────────┘
```

## Memory Types

### Episodic Memory
Past interactions and their outcomes.
```json
{
  "session_id": "abc-123",
  "timestamp": "2026-06-03T20:00:00Z",
  "task": "Fix login bug",
  "outcome": "success",
  "files_modified": ["src/auth/login.ts"],
  "key_decisions": ["Used bcrypt instead of argon2 per project convention"],
  "duration": "12 minutes"
}
```

### Semantic Memory
Facts about the project and codebase.
```json
{
  "fact": "Authentication uses JWT with RS256",
  "source": "src/auth/config.ts",
  "confidence": 0.95,
  "last_verified": "2026-06-03"
}
```

### Procedural Memory
How to accomplish common tasks.
```json
{
  "task_pattern": "Add new API endpoint",
  "steps": [
    "Create route in src/routes/",
    "Add controller in src/controllers/",
    "Add validation schema in src/schemas/",
    "Add test in tests/routes/",
    "Update OpenAPI spec"
  ],
  "learned_from": ["session-001", "session-005"]
}
```

## Integration with Knowledge System

The existing `knowledge/*.yaml` files become the seed data for semantic memory. The memory service loads these on startup and supplements them with agent-learned facts.

## Retrieval Strategy

1. **Task embedding** — Embed the current task description
2. **Similarity search** — Find relevant episodic and semantic memories
3. **Context injection** — Add top-K memories to agent prompt
4. **Recency bias** — Recent memories weighted higher

## Data Lifecycle

- **Write:** After each agent session, extract learnings
- **Read:** Before each session, retrieve relevant memories
- **Decay:** Memories not accessed in 90 days get lower weight
- **Verification:** Periodically check if facts still hold

## Privacy & Security

- All data stored locally on workstation
- No cloud sync (unless explicitly configured)
- Per-project memory isolation
- User can review and delete memories

## Open Questions

1. How to detect and resolve contradictory memories?
2. Optimal context window allocation for injected memories?
3. Should agents self-assess memory quality?
4. Integration with OpenHands' built-in memory (if any)?
