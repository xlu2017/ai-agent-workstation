# Ambient context vendor implementation plan

## Scope

The active vendored ambient-context path is:

```text
control-plane/vendor/ambient-context
```

The current design is intentionally first-party. Vendored projects are optional provider implementations behind `control-plane/ambient/*` collectors, not direct product boundaries. If a vendored package is absent or unbuilt, the collector must still return degraded evidence instead of failing the session.

## Planned ambient-context features

The planned feature set is:

1. Browser state collection from Chrome DevTools Protocol and Playwright.
2. DOM, accessibility, console, network, and page metadata collection without relying on periodic screenshots.
3. Browser element selection for vague prompts such as `fix this`.
4. Drag-region browser selection from the Chrome extension.
5. Screenshot fallback only when DOM/component evidence is unavailable or low confidence.
6. DOM-to-source mapping from explicit framework metadata, source maps, and source hints.
7. Framework-aware source hints for React, Vue, Angular, Vite, Next-style frontends, and app-provided `data-jg-*` annotations.
8. Editor/LSP selection context, diagnostics, symbol, and selected text capture.
9. Terminal command-boundary context, including cwd, command, exit code, stdout/stderr tails, failure summaries, mentioned files, and optional terminal screen reconstruction.
10. Repo/worktree state capture from git status, branch, commit, dirty files, and optional live file change watching.
11. Source code structure and symbol graph extraction for Python, TypeScript, JavaScript, TSX, and JSX.
12. Runtime request tracing and frontend/backend trace correlation using OpenTelemetry when available, with timer-based fallback.
13. Desktop active-window metadata without using screenshots as primary context.
14. Multi-frontend and emulator-aware context packets for web, Android, iOS, and other client views sharing a backend.
15. Redaction before persistence.
16. Append-only ambient event log.
17. Reduced ambient state, evidence graph, and bounded context packet generation.
18. Live-feed mirroring with only user-safe summaries.
19. Ambient vendor status and fetch APIs using server-side GitHub authentication.
20. Browser-side selection history, source hints, confidence scoring, prompt templates, and status feedback.

## Existing first-party implementation

### Core data model

`control-plane/ambient/types.py` already defines source classes, event types, privacy marks, ambient events, evidence graph nodes/edges, and `ContextPacket`. This should remain the stable schema layer.

Important current event types include:

```text
browser.tab_observed
browser.element_selected
browser.console_log
browser.network_request
frontend.interaction
editor.selection_changed
terminal.command_started
terminal.command_completed
repo.state_observed
repo.files_changed
desktop.window_focused
runtime.request_observed
runtime.trace_observed
context.packet_built
screenshot.fallback_captured
```

### Collection orchestration

`AmbientObservationService.collect_once()` already resolves session metadata, repo/worktree paths, branch, browser state, repo state, code structure, desktop state, legacy context, reduced state, evidence graph, and context packet.

Keep this as the single collection orchestrator. New providers should plug into this service or into helpers called by this service.

### API surface

`control-plane/api/ambient.py` already exposes:

```text
GET  /api/sessions/{session_id}/ambient/vendors
POST /api/sessions/{session_id}/ambient/events
POST /api/sessions/{session_id}/ambient/terminal/started
POST /api/sessions/{session_id}/ambient/terminal/completed
POST /api/sessions/{session_id}/ambient/editor/selection
POST /api/sessions/{session_id}/ambient/collect
GET  /api/sessions/{session_id}/ambient/events
GET  /api/sessions/{session_id}/ambient/state
GET  /api/sessions/{session_id}/ambient/context
GET  /api/sessions/{session_id}/ambient/health
```

This is enough for the browser extension, terminal integration, editor bridge, internal planning flow, and debugging UI.

### Vendor registry

`control-plane/ambient/vendor_registry.py` is the runtime registry for vendored providers. It reads `control-plane/vendor/ambient-context/manifest.json`, reports source presence, adds candidate Python paths, and checks module availability.

The API vendor package expects compatibility functions:

```text
load_manifest
list_vendors
get_vendor
source_present
```

These functions must remain available because `control-plane/api/ambient_vendor/registry.py` and `control-plane/api/ambient_vendor/service.py` import them.

## Vendored provider stack and implementation path

### Playwright Python

Manifest id: `playwright_python`

Role: browser CDP, DOM, accessibility, console, network, and page metadata provider.

Current implementation:

`BrowserCdpCollector` already uses vendored/installed Playwright when available and otherwise degrades to direct CDP `/json/list` polling. The current Playwright path captures title, URL, active element, body text tail, links, and buttons.

Implement next:

1. Replace page-level `evaluate()` snapshots with CDP-domain collection through Playwright `new_cdp_session(page)`.
2. Collect `DOMSnapshot.captureSnapshot`, `Accessibility.getFullAXTree`, recent `Runtime.exceptionThrown`, `Log.entryAdded`, and selected `Network` request metadata.
3. Add browser events for `browser.console_log` and `browser.network_request`, not only `browser.tab_observed`.
4. Attach trace/session headers to frontend requests where possible so runtime events can correlate with browser requests.
5. Preserve the direct CDP fallback for unreachable or unsupported Playwright connections.

### source-map

Manifest id: `source_map_js`

Role: JavaScript source-map reference for DOM-to-source mapping.

Current implementation:

`SourceMapResolver` resolves explicit component metadata first, can read local or inline source maps, and currently uses a best-effort fallback that selects source candidates and approximate generated line numbers.

Implement next:

1. Add a small source-map adapter that can call the vendored JavaScript `source-map` library through a Node subprocess or a tiny bundled CLI.
2. Return original source, original line, original column, and symbol name from VLQ mappings.
3. Cache source-map lookups by asset URL and mtime.
4. Wire `SourceMapResolver` into browser element selection and `BrowserCdpCollector` so selected/generated locations become `component.source` hints.

### Tree-sitter

Manifest id: `tree_sitter`

Role: code structure, symbol graph, syntax-aware source mapping.

Current implementation:

`CodeStructureCollector` checks for `tree_sitter`, but Python code uses `ast` and JS/TS/TSX code falls back to text heuristics.

Implement next:

1. Add language-specific Tree-sitter grammars or a parser bundle for Python, JavaScript, TypeScript, and TSX.
2. Replace JS/TS text heuristics with Tree-sitter queries for functions, classes, exports, React components, hooks, routes, and event handlers.
3. Emit richer symbol records with `path`, `name`, `kind`, `line`, `end_line`, `exported`, `imports`, and `references` where feasible.
4. Feed symbols into the evidence graph so a selected component can link to source files, handlers, and tests.

### watchfiles

Manifest id: `watchfiles`

Role: repo/worktree file-change provider.

Current implementation:

`RepoSnapshotCollector` captures git branch, commit, dirty files, and has a one-shot optional `poll_file_changes_once()` using `watchfiles`.

Implement next:

1. Add a per-session long-running watcher owned by the session lifecycle manager.
2. Emit `repo.files_changed` events continuously, batched and debounced.
3. Include git diff stats and current validation status after agent edits.
4. Stop watchers when the session is archived, cancelled, or deleted.

### pygls and python-lsp-server

Manifest ids: `pygls`, `python_lsp_server`

Role: editor/LSP context, Python diagnostics, symbol lookup.

Current implementation:

`build_editor_selection_event()` accepts editor selection payloads, but the server does not yet run a persistent LSP bridge.

Implement next:

1. Add an editor bridge service that accepts Monaco, VS Code, code-server, or pygls-style document sync events.
2. Use `pygls` to normalize LSP messages and `python-lsp-server` for Python diagnostics where available.
3. Persist diagnostics, document version, selection range, current symbol, and nearest enclosing function/class.
4. Add source-to-DOM reverse lookup for selected editor code when the browser page is open.

### pyte

Manifest id: `pyte`

Role: terminal screen reconstruction provider.

Current implementation:

`TerminalObservationBuilder` records command start/completion and uses `pyte` to reconstruct a bounded screen tail when available.

Implement next:

1. Integrate terminal command start/completion endpoints into the actual PTY or shell wrapper used by sessions.
2. Record structured exit code directly from the command runner, not inferred text.
3. Emit `terminal.command_completed` for failing test/lint/typecheck commands before planner retry.
4. Link `mentioned_files` to evidence graph nodes and context-packet `relevant_files`.

### OpenTelemetry Python

Manifest id: `opentelemetry_python`

Role: runtime tracing, FastAPI/ASGI tracing, request correlation.

Current implementation:

`runtime_trace.py` has an OpenTelemetry-aware span helper and a FastAPI middleware helper that emits `runtime.request_observed` when `x-agent-session-id` is present.

Implement next:

1. Mount middleware in the control-plane and app-server processes where session-owned apps are proxied.
2. Ensure frontend/browser requests carry `x-agent-session-id`, `x-agent-worktree-id`, and `x-agent-trace-id`.
3. Store route, handler, status, duration, request id, and related browser network request id.
4. Add trace correlation edges in the evidence graph: browser request -> backend route -> handler/source file.

## Browser extension implementation path

The Chrome extension already implements the intended user flow: right-click, drag select, confirm region, enter prompt, send to the active session.

Next implementation steps:

1. In `page-selector.js`, include `source-hints.js` output in `describeTarget()` so selected elements carry `sourceFile`, `sourceLine`, `componentName`, and hint confidence.
2. Include `confidence.js` summary in the submitted payload.
3. Keep visual fallback bounded to the selected region. Do not persist raw full-page images in history.
4. Add browser-side status polling through `status.js` after submission, using session events or task status endpoints.
5. Ensure chat requests include the ambient event id when event persistence succeeds.
6. Add a backend endpoint that can resolve a selector/source hint to candidate source files before execution, so planning receives a ranked source list instead of raw DOM summaries.

## Evidence graph implementation path

The current evidence graph links sessions to events and events to URLs, selectors, commands, paths, sources, components, and mentioned files.

Next implementation steps:

1. Add edge types for `triggered_request`, `handled_by`, `defined_in`, `selected_in_browser`, `selected_in_editor`, `failed_in_terminal`, and `changed_by_agent`.
2. Add browser network request nodes and runtime trace nodes.
3. Add symbol nodes from Tree-sitter and LSP.
4. Add validation command nodes for tests, lint, and typecheck.
5. Store graph snapshots per session and expose a compact graph endpoint for the UI and planner.

## Planner integration path

The correct integration point is the context packet, not raw event streams.

Execution flow:

```text
user prompt
-> collect ambient context with goal
-> build context packet
-> send packet to prompt router / planning layer
-> planner resolves focus and relevant files
-> control plane validates action permissions
-> executor acts inside the session worktree
-> new terminal/repo/runtime/browser evidence is emitted
-> packet is refreshed after failures or user follow-up
```

Rules:

1. Ambient context may explain what `this` means.
2. Ambient context must not authorize mutation, commit, push, deploy, provider signup, or secret access.
3. Context packets should contain evidence ids and reduced summaries, not unbounded raw logs or full screenshots.
4. Low-confidence evidence should still be usable, but the planner must treat it as a hypothesis.

## Priority order

### P0: make current scaffold reliable

1. Keep the vendor registry compatibility API stable.
2. Verify ambient vendor list/fetch imports cleanly.
3. Mount ambient and ambient vendor routers in the server if not already mounted.
4. Add smoke tests for `GET /api/ambient/vendors`, `POST /api/sessions/{id}/ambient/events`, and `GET /api/sessions/{id}/ambient/context`.
5. Ensure context packets are included in normal session planning for vague prompts.

### P1: browser-selected `fix this`

1. Finish extension source hint inclusion.
2. Add browser selection confidence to ambient event payloads.
3. Wire source-map and Tree-sitter lookup into selected element resolution.
4. Add ranked source-file candidates to context packets.
5. Add tests for selector -> source -> action recommendation flow.

### P2: runtime-aware debugging

1. Mount OpenTelemetry/timer middleware.
2. Correlate browser network requests to backend route events.
3. Link traces to source handlers and terminal failures.
4. Refresh context packets after failed validation commands.

### P3: multi-frontend validation

1. Connect per-frontend ambient streams to the session graph.
2. Add matrix projection for client URL, device profile, health, latest trace, and selected component.
3. Add coordinated validation runs across browser/emulator/simulator clients.
4. Ensure frontend sessions do not contaminate each other through shared browser profile or auth state.

## Verification checklist

Run or add tests for:

```text
python -m py_compile control-plane/ambient/vendor_registry.py
python -m py_compile control-plane/api/ambient_vendor/registry.py
python -m py_compile control-plane/api/ambient_vendor/service.py
pytest control-plane/tests/test_ambient_context.py -q
pytest control-plane/tests/test_ambient_service.py -q
pytest control-plane/tests/test_ambient_bridge_replacement_routes.py -q
```

Manual smoke:

```text
GET  /api/sessions/test-session/ambient/health
GET  /api/sessions/test-session/ambient/vendors
GET  /api/ambient/vendors
POST /api/sessions/test-session/ambient/events
POST /api/sessions/test-session/ambient/collect
GET  /api/sessions/test-session/ambient/context?goal=fix%20this
```

## Non-goals

1. Do not replace Playwright, Tree-sitter, LSP, or OpenTelemetry with custom generic implementations unless integration requires it.
2. Do not treat screenshots as the primary context path.
3. Do not send raw unbounded ambient logs to the model.
4. Do not let ambient evidence bypass worktree, policy, approval, or runtime validation.
5. Do not assume a single browser debug port, desktop availability, or fixed worktree path.
