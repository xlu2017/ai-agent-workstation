# Ambient Context Observation Fabric

## Intent

The platform collects ambient context as structured causal evidence, not as periodic screenshots.

Screenshots are allowed only as explicit or low-confidence fallback artifacts. The primary path is:

```text
browser protocol + DOM + source maps
editor/LSP state
terminal PTY/command state
repo/worktree/git state
runtime traces/logs/network events
desktop window metadata
session event log
```

## Control-plane boundary

```text
jubilant-goggles
  owns collection, session scoping, redaction, policy, runtime validation, and execution

agent-core
  consumes context packets, searches memory/context, validates action contracts, and recommends plans/actions
```

Ambient context can explain what the session is seeing. It must not authorize filesystem mutation, commits, pushes, deploys, secrets access, or provider actions.

## Implemented runtime flow

```text
POST /api/sessions/{session_id}/ambient/collect
  -> AmbientObservationService.collect_once
  -> browser/repo/desktop/legacy-context collectors
  -> redaction
  -> ambient/events.jsonl
  -> live-feed ambient_context_collected mirror
  -> ambient/state.json
  -> ambient/evidence_graph.json
  -> ambient/context_packet.json
```

Read endpoints:

```text
GET /api/sessions/{session_id}/ambient/events
GET /api/sessions/{session_id}/ambient/state?collect=true
GET /api/sessions/{session_id}/ambient/context?goal=fix%20this&collect=true
GET /api/sessions/{session_id}/ambient/health
```

The same service can also be called internally:

```python
from ambient.service import AmbientObservationService

result = AmbientObservationService().collect_once("session-id", goal="fix this")
```

## Tool and library choices

| Responsibility | Primary tool/library | Why | Fallback |
|---|---|---|---|
| Browser state, DOM, console, network | Chrome DevTools Protocol through Playwright CDPSession | CDP is the native structured protocol for Chromium inspection; Playwright gives stable Python control and CDP access | Direct CDP `/json/list` polling across configured endpoints |
| DOM and accessibility context | CDP `DOM`, `DOMSnapshot`, `Accessibility`, `Runtime`, `Network`, `Log`, `Page` domains | Captures semantic page state without pixels | Browser extension content script |
| DOM-to-source mapping | source maps plus framework dev metadata | Maps generated browser locations back to source files | UI bridge service lookup only |
| Frontend framework context | Dev-only SDK for React/Vite/Next apps | Captures component stack, route, interaction, and trace id at source | Browser DOM/accessibility only |
| Runtime request tracing | OpenTelemetry plus FastAPI/ASGI middleware | Standard trace context and request correlation | Local middleware emitting session events only |
| Repo/worktree file changes | `watchfiles` | Fast cross-platform file watching backed by Rust notify | `git status --porcelain` polling |
| Code structure and symbol graph | Tree-sitter | Incremental multi-language concrete syntax trees | ripgrep/BM25 and LSP references |
| Editor/LSP context | `pygls`/LSP-compatible bridge | Python implementation for LSP-compatible messages and document sync | editor-specific HTTP bridge |
| Terminal state | shell integration + PTY event capture, optional `pyte` for terminal screen reconstruction | Command boundaries, cwd, exit code, stack traces, and mentioned files are more useful than terminal screenshots | stdout/stderr chunk capture and legacy latest-terminal-context.md |
| Desktop active window | `xdotool`, `wmctrl`, `xprop`, process inspection | Captures active app/window/process without screenshots | degraded metadata event when no X11 desktop is available |
| Event/schema validation | Pydantic models | Matches the existing control-plane stack | JSON schema at API boundary |
| Redaction | deterministic regex and field-name redaction first | Prevents secret leakage before persistence | optional later secret scanner |

## Resilience contract

The ambient layer must survive server changes.

Rules:

```text
No single browser port is authoritative.
No desktop command is required for collection to succeed.
No worktree path is assumed without session metadata fallback.
No external service failure should fail the entire collection pass.
Every collector returns either evidence or a degraded status.
Reduced outputs are written atomically.
Raw ambient events are redacted before persistence.
Legacy latest-*-context.md files remain valid input.
```

Configuration is environment-backed:

```text
SESSIONS_DIR=/opt/workstation/sessions
REPOS_DIR=/opt/workstation/repos
BRIDGE_URL=http://127.0.0.1:9876
AMBIENT_BROWSER_DEBUG_URLS=http://127.0.0.1:9222,http://127.0.0.1:9223
AMBIENT_BROWSER_TIMEOUT_SECONDS=1.5
AMBIENT_BROWSER_ENABLED=true
AMBIENT_DESKTOP_ENABLED=true
AMBIENT_REPO_ENABLED=true
AMBIENT_LEGACY_CONTEXT_ENABLED=true
AMBIENT_RUNTIME_ENABLED=true
AMBIENT_MAX_EVENTS_PER_COLLECT=100
```

## Storage model

```text
<sessions_dir>/<session_id>/ambient/events.jsonl
  append-only ambient event log

<sessions_dir>/<session_id>/ambient/state.json
  latest reduced browser/editor/terminal/repo/desktop/runtime state

<sessions_dir>/<session_id>/ambient/evidence_graph.json
  causal graph nodes and edges

<sessions_dir>/<session_id>/ambient/context_packet.json
  bounded model/planner context packet

<sessions_dir>/<session_id>/events/events.jsonl
  canonical user-visible execution/live-feed event stream
```

The ambient log is richer than the transcript. The live-feed mirror contains only user-safe summaries and references.

## Event classes

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

## Context packet contract

A context packet is the bounded object sent into planning and routing. It includes:

```text
goal
session id
repo/worktree/branch
ambient focus
recent observations
relevant files
runtime trace ids
evidence event ids
confidence and privacy marks
```

The model should not receive raw unbounded event streams.

## Screenshot policy

Default:

```text
periodic screenshots: disabled
```

Allowed triggers:

```text
user explicitly asks what is on screen
visual regression evidence is needed
DOM/accessibility/source-map context is unavailable
browser/desktop collector confidence is low
before/after visual UI proof is needed
```

All screenshots must be session-scoped, short-retention, and redacted where possible. Screenshots are evidence, not primary context.

## Implemented files

```text
control-plane/ambient/
  config.py
  types.py
  redaction.py
  event_log.py
  reducers.py
  evidence_graph.py
  context_packet.py
  source_mapping.py
  legacy_context.py
  service.py
  collectors/
    browser_cdp.py
    editor_bridge.py
    terminal_collector.py
    repo_watcher.py
    desktop_window.py
    runtime_trace.py

control-plane/api/ambient.py
control-plane/tests/test_ambient_context.py
control-plane/tests/test_ambient_service.py
requirements-ambient-optional.txt
```
