# Server app launcher scaffold

The server app launcher lets the session right panel expose common remote-desktop applications as searchable tabs.

## User behavior

1. Open a session page.
2. The right panel gains an `Apps` tab beside `Worklog`, `Changes`, and `Desktop`.
3. Search for canonical app intents such as Terminal, Web Browser, File Manager, Code Editor, System Monitor, Screenshot Tool, or Settings.
4. The app list reports resolver confidence: `running`, `installed`, or `catalog_only`.
5. Selecting an app opens an app-specific right-panel tab.
6. The app tab submits a normal session chat instruction, such as `Open a terminal on the remote desktop`, so the existing desktop-control routing path can perform the launch.
7. Any remote desktop or app tab can be opened in a separate browser window using the `Pop out` control.

## Frontend files

```text
control-plane/web/src/server-app-catalog.ts
control-plane/web/src/server-app-launcher-enhancer.ts
control-plane/web/src/server-app-panel.ts
control-plane/web/src/server-app-launcher.css
```

The enhancer intentionally degrades gracefully. It first attempts:

```text
GET /api/session-graph/platform-apps
```

If that endpoint is not present, it uses the bundled popular-app catalog and still works through the existing session chat endpoint.

## Backend resolver

```text
control-plane/api/services/platform_apps.py
control-plane/api/routes/session_graph/platform_apps.py
```

The service provides:

```python
discover_popular_applications(query: str = "")
resolve_popular_applications(query: str = "")
launch_popular_application(app_id: str)
```

The resolver is canonical-intent based rather than command-name based. For example, the canonical `Terminal` app can resolve to `xfce4-terminal`, `gnome-terminal`, `konsole`, `mate-terminal`, `lxterminal`, `x-terminal-emulator`, `xterm`, or other known distro variants.

Resolution combines these signals:

```text
1. PATH lookup via shutil.which
2. .desktop file parsing
3. .desktop Name, GenericName, Categories, Keywords, and Exec metadata
4. distro alternatives/fallbacks such as x-terminal-emulator, x-www-browser, sensible-browser, editor, and xdg-open
5. process scan via ps -eo pid,comm,args
6. optional visible-window scan via wmctrl -lx when available
```

The response includes explicit evidence:

```json
{
  "id": "terminal",
  "installed": true,
  "running": false,
  "confidence": "installed",
  "launchCommand": "x-terminal-emulator",
  "matchedCommands": ["x-terminal-emulator", "xterm"],
  "matchedDesktopFiles": ["/usr/share/applications/org.xfce.Terminal.desktop"],
  "matchedProcesses": [],
  "matchedWindows": []
}
```

Launch is allowlist-based. It only attempts commands defined by the canonical app resolver and sets the remote desktop environment:

```text
DISPLAY=:10
XAUTHORITY=/home/agent/.Xauthority
```

## Route wiring

The platform apps endpoint is owned by the decomposed session graph router:

```python
GET /api/session-graph/platform-apps?q=terminal
```

The route is registered through `api/routes/session_graph/router.py`, which includes `api/routes/session_graph/platform_apps.py`. The route delegates to `api/services/platform_apps.py` for resolver logic.

The old `api.session_graph` import path is now a small compatibility wrapper around `api.routes.session_graph.router`, so legacy tests or imports keep working without preserving the former monolithic route file.

The frontend calls this route and falls back to its bundled catalog only if the backend route returns an error.

## Route module layout

Large route files are intentionally split so future agents can safely make whole-file replacement edits to isolated route domains.

### Top-level API routes (`api/routes/`)

```text
api/routes/health.py           — GET /api/health
api/routes/remote_desktop.py   — /api/v2/remote-desktop/*
api/routes/sessions.py         — /api/sessions/* (CRUD, chat, interrupt)
api/routes/session_events.py   — /api/sessions/*/events, timeline, transcript
api/routes/services.py         — /api/services/* (list, start, stop, restart, update)
api/routes/models.py           — GET /api/models
api/routes/knowledge.py        — /api/knowledge/*
api/routes/filesystem.py       — /api/browse, /api/logs, /api/open-file-manager, /api/pick-folder
```

### Session graph sub-routes (`api/routes/session_graph/`)

```text
api/routes/session_graph/router.py        — composite router (includes all sub-routers)
api/routes/session_graph/helpers.py       — shared helpers, context, visibility checks
api/routes/session_graph/sessions.py      — session CRUD
api/routes/session_graph/edges.py         — edge CRUD
api/routes/session_graph/projections.py   — context projection CRUD
api/routes/session_graph/adapters.py      — mount, unmount, adapt, adapter mappings
api/routes/session_graph/events.py        — event listing
api/routes/session_graph/settings.py      — observability settings
api/routes/session_graph/platform_apps.py — platform app discovery
api/routes/session_graph/snapshot.py      — graph snapshot, session-update apply
```

### Shared modules

```text
api/config.py                       — shared constants (paths, URLs, env defaults)
api/services/remote_desktop.py      — Guacamole config, token, health-check helpers
api/services/process_control.py     — service start/stop/restart, port-check helpers
api/services/platform_apps.py       — canonical app resolver
```

## Tests

```text
control-plane/tests/test_api_route_composition.py
control-plane/tests/test_server_apps_panel.py
control-plane/tests/test_platform_apps_service.py
control-plane/tests/test_remote_desktop.py
control-plane/tests/test_session_graph.py
control-plane/tests/test_session_graph_crud_api.py
```

These tests verify frontend wiring, canonical search behavior, `.desktop` alias matching, process detection, resolver evidence fields, route ownership, remote desktop endpoints, and session graph CRUD operations.
