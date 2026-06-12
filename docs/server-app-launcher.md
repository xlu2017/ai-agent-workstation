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
control-plane/api/platform_apps_routes.py
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

`control-plane/api/platform_apps_routes.py` exposes the discovery route with the same frontend contract:

```python
GET /api/session-graph/platform-apps?q=terminal
```

The current right-panel frontend calls this route opportunistically and falls back to its bundled catalog if the router is not included by the running FastAPI entrypoint.

## Tests

```text
control-plane/tests/test_server_apps_panel.py
control-plane/tests/test_platform_apps_service.py
```

These tests verify frontend wiring, canonical search behavior, `.desktop` alias matching, process detection, and resolver evidence fields.
