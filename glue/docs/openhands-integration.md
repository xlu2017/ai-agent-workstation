# OpenHands Integration

## Current State

OpenHands is deployed via Docker on the workstation:
- Container: `openhands` on port 3000
- Workspace mount: `/home/agent/projects` → `/opt/workspace_base` inside container
- Model: DeepSeek V4-Flash via LiteLLM on port 4000

## Integration Approach

### Level 1: File-Based Context (Implemented)

The simplest integration: place UI context files where OpenHands can read them.

**How it works:**
1. UI event arrives at bridge service
2. Bridge writes `latest-ui-context.md` to session context directory
3. Symlink or copy the context file into OpenHands workspace
4. Agent reads the file when instructed

**Setup:**
```bash
# Create symlink from session context to OpenHands workspace
ln -sf /opt/workstation/sessions/<session>/context /home/agent/projects/ui-context
```

Then tell the agent: "Read `ui-context/latest-ui-context.md` for the element I just selected."

### Level 2: Workspace Mount Mapping (Future)

Map each session's context directory into the OpenHands container:

```yaml
# docker-compose override
services:
  openhands:
    volumes:
      - /opt/workstation/sessions:/opt/sessions:ro
```

Agent can then read any session's context at `/opt/sessions/<id>/context/`.

### Level 3: OpenHands API Integration (Future)

Use OpenHands REST API to inject context into active conversations:

```python
# Hypothetical — depends on OpenHands API availability
import requests

def inject_ui_context(session_id, context_md):
    requests.post(f"http://localhost:3000/api/sessions/{session_id}/message", json={
        "role": "user",
        "content": f"The user just inspected a UI element. Here's the context:\n\n{context_md}"
    })
```

### Level 4: Custom Microagent (Future)

Create an OpenHands microagent that:
- Watches for new UI events (file watcher or polling)
- Automatically reads context
- Takes action (opens file, suggests changes)

## OpenHands Workspace Convention

OpenHands agents can read files from their workspace. The convention:

```
/opt/workspace_base/
├── <project files>
└── .openhands/
    └── ui-context/           # Our context files
        ├── latest-ui-context.md
        └── ui-events.jsonl
```

## Security Notes

- Context files are read-only from the agent's perspective
- No secrets in context files (only source paths, component names, URLs)
- Agent cannot modify the bridge service or extension

## Limitations

1. OpenHands currently requires manual instruction to read context files
2. No automatic trigger when new UI events arrive
3. Context is per-session but OpenHands may not be session-aware
4. File-based approach has latency (write delay + agent poll)
