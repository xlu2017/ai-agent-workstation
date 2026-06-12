# Server app launcher scaffold

The server app launcher lets the session right panel expose common remote-desktop applications as searchable tabs.

## User behavior

1. Open a session page.
2. The right panel gains an `Apps` tab beside `Worklog`, `Changes`, and `Desktop`.
3. Search for common apps such as Terminal, Web Browser, File Manager, Code Editor, System Monitor, Screenshot Tool, or Settings.
4. Selecting an app opens an app-specific right-panel tab.
5. The app tab submits a normal session chat instruction, such as `Open a terminal on the remote desktop`, so the existing desktop-control routing path can perform the launch.
6. Any remote desktop or app tab can be opened in a separate browser window using the `Pop out` control.

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

## Backend scaffold

```text
control-plane/api/services/platform_apps.py
```

The service provides:

```python
discover_popular_applications(query: str = "")
launch_popular_application(app_id: str)
```

Discovery checks allowlisted popular desktop apps against PATH and `.desktop` files under:

```text
/usr/share/applications
~/.local/share/applications
```

Launch is allowlist-based. It only attempts commands defined in the catalog and sets the remote desktop environment:

```text
DISPLAY=:10
XAUTHORITY=/home/agent/.Xauthority
```

## Intended route wiring

The route can be wired into the existing session graph router without changing the frontend contract:

```python
from api.services.platform_apps import discover_popular_applications, launch_popular_application

@router.get("/platform-apps")
def list_platform_apps(q: str = ""):
    return {"applications": discover_popular_applications(q)}

@router.post("/platform-apps/{app_id}/launch")
def launch_platform_app(app_id: str):
    return launch_popular_application(app_id)
```

The frontend already calls `GET /api/session-graph/platform-apps` opportunistically and falls back when it is unavailable.

## Tests

```text
control-plane/tests/test_server_apps_panel.py
control-plane/tests/test_platform_apps_service.py
```

These tests verify frontend wiring and catalog discovery behavior.
