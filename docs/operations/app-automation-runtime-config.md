# App automation runtime configuration

App automation can now run in three modes:

```text
mock mode
  APP_AUTOMATION_MOCK=true
  returns deterministic completed results without vendor dispatch

live configured mode
  vendor endpoint or command configured by environment or saved control-plane config
  dispatches the normalized action envelope to that runtime

local vendored adapter mode
  source/jubilant_goggles_adapter.py exists and local adapters are enabled
  exercises the vendor boundary without external side effects
```

## Configuration source order

For each configurable vendor, runtime dispatch resolves configuration in this order:

```text
1. Environment variable
2. Stored server-side control-plane config
3. Local vendored adapter fallback
4. runtime_not_configured
```

Environment variables always win. Stored values are for operator-managed development and workstation deployments where updating process environment is inconvenient.

## API endpoints

```text
GET    /api/app-automation/config
GET    /api/app-automation/config/{vendor_id}
PUT    /api/app-automation/config/{vendor_id}
DELETE /api/app-automation/config/{vendor_id}
```

`GET /api/app-automation/vendors` also embeds each vendor's `runtime_config` summary.

Stored configuration is written to:

```text
/opt/workstation/config/app-automation-runtime.json
```

Override the location with:

```text
APP_AUTOMATION_CONFIG_PATH=/path/to/app-automation-runtime.json
```

The server attempts to write the file with `0600` permissions.

## Configurable vendors

| Vendor | Field | Environment override | Stored kind |
| --- | --- | --- | --- |
| Composio | Composio proxy URL | `COMPOSIO_PROXY_URL` | URL |
| Activepieces | Activepieces webhook URL | `ACTIVEPIECES_WEBHOOK_URL` | URL |
| n8n | n8n webhook URL | `N8N_WEBHOOK_URL` | URL |
| Stagehand | Stagehand command | `STAGEHAND_COMMAND` | command |
| Browser Use | Browser Use command | `BROWSER_USE_COMMAND` | command |
| Skyvern | Skyvern command | `SKYVERN_COMMAND` | command |

`mcp_servers` is not configured through this endpoint. Its live GitHub path uses the platform repo provider authentication.

## UI behavior

The dashboard now mounts a global app-automation configuration helper.

It exposes a floating **Configure app automation** button when configurable vendors are unconfigured. It also intercepts app-automation execute responses that return:

```text
status = runtime_not_configured
error.code = RUNTIME_NOT_CONFIGURED
```

When that happens, the UI opens a modal for the selected vendor and asks the user for the missing URL or command.

The modal intentionally does not expose full stored values back to the browser. It shows only a redacted preview. To change a value, enter a replacement.

## Security notes

Use controlled internal endpoints and commands. Do not put arbitrary public webhook URLs or shell snippets into the runtime config unless they are part of the trusted workstation deployment.

For command vendors, the command runs from the vendored source tree and receives the normalized action envelope as JSON on stdin. Treat these commands as trusted local adapters.

## Validation

Run:

```bash
cd control-plane
pytest tests/test_app_automation.py tests/test_app_automation_config.py -q
```

Frontend validation:

```bash
cd control-plane/web
pnpm build
```
