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
POST /api/app-automation/execute
```

The execute endpoint now has a committed-vendor scaffold path:

1. action lookup
2. vendor route plan construction
3. risk classification
4. approval gate
5. dry-run plan
6. vendor source presence check
7. platform-owned adapter scaffold dispatch
8. normalized scaffold result

Live runtime invocation is still intentionally blocked until one vendor adapter is explicitly wired and tested.

## Routing scaffold files

```text
control-plane/api/app_automation/models.py
control-plane/api/app_automation/vendor_plan.py
control-plane/api/app_automation/adapter_base.py
control-plane/api/app_automation/vendor_adapters.py
control-plane/api/app_automation/executor.py
```

`vendor_plan.py` defines the capability matrix and per-action fallback chain. `adapter_base.py` defines the normalized health/result contract. `vendor_adapters.py` declares one adapter class per selected provider. `executor.py` dispatches approved non-dry-run requests into the selected scaffolded adapter once source is present.

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

External side effects require approval before live execution. Dry runs are always allowed.

## License review

Before redistributing modified source, review the upstream license for each selected tool. n8n and Skyvern require special attention because their licenses may impose obligations that differ from permissive MIT/Apache-style libraries.

## Next implementation pass

Wire one real provider at a time:

1. MCP read-only action through vendored MCP reference servers.
2. Composio read-only API action.
3. Activepieces workflow dry-run/live run boundary.
4. Stagehand or Browser Use browser action with a controlled browser profile.
5. Skyvern visual-browser fallback only after browser/API alternatives are wired.

Each live adapter must include unavailable, dry-run, approval-blocked, success, and event-log tests.
