# Glue deprecation coverage audit

`glue/` is deprecated without migration. This audit records whether each surviving responsibility has an active control-plane replacement.

## Decision

`glue/` can remain deprecated and should not receive new product work.

The active replacements are now sufficiently present for product development to happen outside this folder. Some legacy convenience commands are intentionally not preserved because they create split-brain `session.json` state.

## Coverage matrix

| Legacy glue responsibility | Legacy file(s) | Replacement | Coverage | Notes |
| --- | --- | --- | --- | --- |
| Session list/create/destroy/inspect | `glue/bin/glue` | `/api/session-graph/sessions`, `control-plane/api/routes/session_graph/sessions.py` | Covered for canonical identity | The old CLI wrote direct `session.json` metadata and is intentionally not migrated. New code must create graph sessions/facets instead. |
| Bridge start/status | `glue/bin/glue`, `glue/ui-bridge/server.py` | `control-plane/api/server.py`, `/api/health`, `/api/services`, repo-backed service controls | Covered | The standalone `:9876` bridge is not a product service. Control-plane FastAPI is the only active API surface. |
| Browser selection/inspect events | `glue/ui-bridge/server.py` | `control-plane/extension/*`, `POST /api/sessions/{session_id}/ambient/events` | Covered | The extension writes structured ambient events directly to the control plane. The ambient router is mounted before the deprecated `/api/sessions` catch-all. |
| Editor focus/selection context | `glue/ui-bridge/server.py` `/editor-context` | `POST /api/sessions/{session_id}/ambient/editor/selection`, `control-plane/ambient/collectors/editor_bridge.py` | Covered | Added typed route for active editor selection ingestion. |
| Terminal command failure capture | `glue/terminal-watcher/*` | `POST /api/sessions/{session_id}/ambient/terminal/started`, `POST /api/sessions/{session_id}/ambient/terminal/completed`, `control-plane/ambient/collectors/terminal_collector.py` | Covered | The active path captures command boundary telemetry instead of scraping tmux panes. Shell hooks can be rewritten against these endpoints if needed. |
| Markdown latest context compatibility | `latest-ui-context.md`, `latest-editor-context.md`, `latest-terminal-context.md` | `control-plane/ambient/legacy_context.py` | Covered as compatibility input | Legacy files are read as low-confidence ambient observations only. New code should write structured ambient events. |
| UI event log and session-scoped context | `events.jsonl`, `ui-events.jsonl`, context markdown | `control-plane/ambient/event_log.py`, `ambient/state.json`, `ambient/evidence_graph.json`, `ambient/context_packet.json`, live-feed mirror events | Covered | Active storage is richer and session-scoped; user-visible summaries mirror into live feed. |
| MCP gateway pointing at glue services | `glue/mcp-gateway.json` | `control-plane/vendor/app-automation`, `/api/app-automation/*`, visual automation routes, future MCP client runtime | Partially covered | The old JSON references glue paths and several missing services. Keep only as historical intent. Do not run it. |
| Playwright/browser automation intent | `glue/mcp-gateway.json` references `playwright-mcp` | `control-plane/api/visual_automation/*`, `control-plane/vendor/app-automation/stagehand`, `browser_use`, `skyvern` placeholders | Covered as scaffold | Live provider and xdotool scaffolds exist. Playwright-specific GUI execution still belongs in active visual automation, not glue. |
| Knowledge/postmortem intent | `glue/mcp-gateway.json` references `knowledge-system` | `control-plane/api/routes/knowledge.py`, settings knowledge UI, app automation vendor scaffold | Covered enough for deprecation | This was only a gateway reference in glue, not an implemented service in this folder. |
| PR courtroom, ownership map, black-box recorder, timeline, service leasing, ask-app | `glue/mcp-gateway.json` only | App automation vendor scaffold, session graph events/projections, repo/service routes, future active modules | Not implemented as product behavior in glue; not a blocker | These were catalog intentions, not usable checked-in services. Preserve in docs only if needed. |

## Verification added during this audit

Active ambient replacement routes were mounted and tested:

```text
POST /api/sessions/{session_id}/ambient/events
POST /api/sessions/{session_id}/ambient/terminal/started
POST /api/sessions/{session_id}/ambient/terminal/completed
POST /api/sessions/{session_id}/ambient/editor/selection
```

Regression coverage:

```text
control-plane/tests/test_ambient_bridge_replacement_routes.py
```

## Deprecation rules for `glue/`

Allowed:

1. Historical documentation.
2. Audit notes like this file.
3. Temporary pointers to active replacements.
4. Eventual deletion after references are confirmed absent.

Not allowed:

1. New runtime behavior.
2. New setup instructions that start `/opt/workstation/glue` services.
3. New dependencies on `:9876` bridge routes.
4. New code writing legacy `session.json` metadata.
5. New MCP gateway entries pointing to `glue/*` paths.

## Recommended next step

Delete or archive the executable glue code in a follow-up once repository references to `/opt/workstation/glue`, `glue session`, and port `9876` are either removed or explicitly quarantined as historical docs.
