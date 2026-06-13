# App automation vendor stack

The app automation scaffold chooses a wide-coverage vendor stack and provides a control-plane abstraction for prompt-to-app execution.

## Selected tools

The source of truth is:

```text
control-plane/vendor/app-automation/manifest.json
```

Selected tools:

| Tool | Layer | Role | Execution kinds |
| --- | --- | --- | --- |
| Composio | API | API toolkit and app account bridge | API, MCP |
| MCP reference servers | MCP | protocol examples and local/server tool references | MCP |
| Activepieces | Workflow | connector workflows and approval-capable automations | workflow, MCP |
| n8n | Workflow | deterministic long-running workflows and webhooks | workflow |
| Stagehand | Browser | TypeScript browser-agent SDK for DOM-aware web apps | browser |
| Browser Use | Browser | Python browser-agent runtime | browser |
| Skyvern | Visual browser | screenshot/vision fallback for brittle web apps | browser, visual_browser |

The stack intentionally covers APIs, MCP, deterministic workflows, browser automation, and visual browser fallback.

## How the vendors work together

The control plane treats these vendors as a ladder, not as peers that all run at once.

```text
api -> mcp -> workflow -> browser -> visual_browser -> desktop
```

Default coordination rules:

1. Prefer native API execution when an app has a reliable API surface.
2. Use MCP when a tool protocol boundary is useful or the tool is local/server-oriented.
3. Use workflow engines for repeatable multi-step app automations.
4. Use browser agents when there is no reliable API/MCP route.
5. Use visual browser automation only when DOM/browser automation is insufficient.
6. Use desktop automation only as a final fallback.

## Vendor responsibilities

### Composio

Use for API-first SaaS actions such as Gmail search, Slack actions, Linear, Notion, HubSpot, and Google Calendar. It should usually be the first choice for stable read-only or account-scoped app actions.

### MCP reference servers

Use for protocol-level tools and local/server tool examples. MCP schema validation is not authorization; the platform must still validate policy, workspace, app, and approval requirements.

### Activepieces

Use for connector workflows, approval-friendly flows, and app-to-app automation. It is the preferred workflow vendor for Google Sheets append, Jira create issue, Discord send message, and similar deterministic automations.

### n8n

Use for larger self-hosted or webhook-heavy workflows after license and deployment review. It is a secondary workflow route behind Activepieces for most current seed actions.

### Stagehand

Use for DOM-aware browser workflows when API/MCP coverage is absent. It should usually run before Browser Use and Skyvern for normal web-app pages.

### Browser Use

Use as a Python-native browser automation fallback for natural-language web navigation when Stagehand is not the right runtime.

### Skyvern

Use as visual-browser fallback for unstable DOMs and pages where visual evidence is more reliable than selectors. Do not make it the default while API/MCP/browser routes are available.

## Current vendored-source status

The selected provider source trees are present under:

```text
control-plane/vendor/app-automation/<tool>/source
```

The control-plane detects vendor presence by checking for source entrypoints such as:

```text
.git
package.json
pyproject.toml
```

Current evidence from checked-in source:

| Tool | Evidence |
| --- | --- |
| Activepieces | `source/package.json` with `name=activepieces` |
| Composio | `source/pyproject.toml` with workspace members |
| MCP servers | `source/README.md` reference server catalog |
| n8n | `source/package.json` with `name=n8n-monorepo` |
| Stagehand | `source/package.json` with `name=stagehand-workspace` |
| Browser Use | `source/pyproject.toml` with `name=browser-use` |
| Skyvern | `source/pyproject.toml` with `name=skyvern` |

## Local vendored adapter contract

Each vendored source tree now contains:

```text
control-plane/vendor/app-automation/<tool>/source/jubilant_goggles_adapter.py
```

These adapter files are intentionally committed inside the vendored source trees. They are the first local patch surface for each vendor. They accept a normalized action envelope on stdin and return a normalized JSON result on stdout.

The local adapter contract exists to make non-dry-run routing testable end-to-end without needing external SaaS accounts, workflow servers, browser agents, or visual automation credentials. The local contract does **not** perform external side effects. It returns:

```text
status = adapter_contract_completed
external_side_effect_performed = false
```

Use this status as “control-plane-to-vendor-boundary works,” not as “the external app was mutated.”

Disable local adapters with:

```bash
APP_AUTOMATION_LOCAL_VENDOR_ADAPTERS=false
```

Then the system returns `runtime_not_configured` unless the vendor-specific live endpoint or command is configured.

## Control-plane abstraction

Platform-owned code lives under:

```text
control-plane/api/app_automation
control-plane/api/routes/app_automation.py
```

Endpoints:

```text
GET  /api/app-automation/vendors
GET  /api/app-automation/capabilities
GET  /api/app-automation/actions
GET  /api/app-automation/actions/{action_id}/plan
GET  /api/app-automation/events/{session_id}
POST /api/app-automation/execute
```

The execute endpoint now performs:

1. action lookup
2. vendor route plan construction
3. action parameter contract validation
4. risk classification
5. approval gate
6. dry-run plan
7. vendor source presence check
8. platform-owned runtime adapter dispatch
9. local vendored adapter dispatch when live vendor runtime is not configured
10. normalized runtime result
11. redacted session audit event persistence

## Runtime adapter files

```text
control-plane/api/app_automation/models.py
control-plane/api/app_automation/vendor_plan.py
control-plane/api/app_automation/adapter_base.py
control-plane/api/app_automation/vendor_adapters.py
control-plane/api/app_automation/runtime.py
control-plane/api/app_automation/event_log.py
control-plane/api/app_automation/executor.py
```

`vendor_plan.py` defines the capability matrix and per-action fallback chain. `adapter_base.py` defines the normalized health/result contract. `runtime.py` implements mock, live, configured endpoint/command, and local vendored adapter dispatch. `event_log.py` writes redacted session events. `executor.py` validates, gates, audits, and dispatches approved non-dry-run requests into the selected adapter once source is present.

## App automation audit events

When `session_id` is present on an execute request, the executor writes app automation events into the normal session event log:

```text
app_automation_planned
app_automation_validation_failed
app_automation_blocked
app_automation_executed
app_automation_failed
```

The event payload records the app, action, selected vendor, route candidates, risk, approval mode, dry-run state, status, and normalized result/error fields. Sensitive parameter keys are redacted before persistence, including token, secret, password, API key, credential, bearer, authorization, access token, refresh token, and client secret fields.

Use:

```text
GET /api/app-automation/events/{session_id}
```

for the app-automation-only audit slice. Raw session timelines still live in the general session event log.

## End-to-end runtime paths

The following paths are now implemented:

| Vendor | End-to-end path |
| --- | --- |
| MCP servers | `github.search_repo` uses the GitHub Search API through server-side repo provider auth when not mocked; `github.create_issue` is implemented behind the approval gate. Unsupported MCP actions can still exercise the local vendored adapter contract. |
| Composio | Uses `COMPOSIO_PROXY_URL` as a controlled HTTP runtime endpoint for normalized action envelopes; otherwise uses `source/jubilant_goggles_adapter.py` for local contract completion. |
| Activepieces | Uses `ACTIVEPIECES_WEBHOOK_URL` as a controlled workflow endpoint; otherwise uses `source/jubilant_goggles_adapter.py` for local contract completion. |
| n8n | Uses `N8N_WEBHOOK_URL` as a controlled workflow endpoint; otherwise uses `source/jubilant_goggles_adapter.py` for local contract completion. |
| Stagehand | Uses `STAGEHAND_COMMAND`, a controlled command that receives the action envelope as JSON on stdin; otherwise uses `source/jubilant_goggles_adapter.py` for local browser-contract completion without launching a browser. |
| Browser Use | Uses `BROWSER_USE_COMMAND`, a controlled command that receives the action envelope as JSON on stdin; otherwise uses `source/jubilant_goggles_adapter.py` for local browser-contract completion without launching a browser. |
| Skyvern | Uses `SKYVERN_COMMAND`, a controlled command that receives the action envelope as JSON on stdin; otherwise uses `source/jubilant_goggles_adapter.py` for local visual-browser-contract completion without launching a browser. |

For deterministic local validation without external services:

```bash
APP_AUTOMATION_MOCK=true
```

Mock mode returns `completed` results for approved non-dry-run actions without external side effects. Local vendored adapters are different: they run vendor-owned adapter files and return `adapter_contract_completed`.

## Seed app action routing

Examples:

| Action | Vendor ladder |
| --- | --- |
| `github.search_repo` | MCP servers -> Composio |
| `slack.send_message` | Composio -> Activepieces -> n8n |
| `google_sheets.append_row` | Activepieces -> Composio -> n8n |
| `web.perform_task` | Stagehand -> Browser Use -> Skyvern |
| `web.visual_task` | Skyvern -> Stagehand -> Browser Use |

## Approval policy

App actions include risk labels:

- `read_only`
- `modification`
- `external_side_effect`

External side effects require approval before live execution. Dry runs are always allowed. Parameter schema validity means only that the action contract is well formed; runtime safety, app credentials, user/session permission, and approval are still enforced by the control plane.

## License review

Before redistributing modified source, review the upstream license for each selected tool. n8n and Skyvern require special attention because their licenses may impose obligations that differ from permissive MIT/Apache-style libraries.

## Validation

Run:

```bash
cd control-plane
pytest tests/test_app_automation.py -q
```

Useful modes:

```bash
APP_AUTOMATION_MOCK=true pytest tests/test_app_automation.py -q
APP_AUTOMATION_LOCAL_VENDOR_ADAPTERS=false pytest tests/test_app_automation.py -q
```

Unset `APP_AUTOMATION_MOCK` and configure the provider-specific endpoint/command variables to test real external runtimes.
