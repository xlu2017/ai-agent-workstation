# App automation vendor stack

The app automation scaffold chooses a wide-coverage vendor stack and provides a control-plane abstraction for prompt-to-app execution.

## Selected tools

The source of truth is:

```text
control-plane/vendor/app-automation/manifest.json
```

Selected tools:

| Tool | Role | Execution kinds |
| --- | --- | --- |
| Activepieces | workflow engine and MCP-capable connector/piece catalog | workflow, MCP |
| Composio | app API toolkit and auth bridge | API, MCP |
| MCP reference servers | reference server catalog and protocol examples | MCP |
| n8n | deterministic workflow engine | workflow |
| Stagehand | TypeScript browser-agent SDK | browser |
| Browser Use | Python browser-agent runtime | browser |
| Skyvern | visual browser workflow runtime | browser, visual browser |

The stack intentionally covers APIs, MCP, deterministic workflows, browser automation, and visual browser fallback.

## Current vendored-source status

The selected provider source trees are now present under:

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
GET  /api/app-automation/actions
POST /api/app-automation/execute
```

The execute endpoint now has a committed-vendor scaffold path:

1. action lookup
2. vendor selection
3. risk classification
4. approval gate
5. dry-run plan
6. vendor source presence check
7. platform-owned adapter scaffold dispatch
8. normalized scaffold result

Live runtime invocation is still intentionally blocked until one vendor adapter is explicitly wired and tested.

## Adapter scaffold files

```text
control-plane/api/app_automation/adapter_base.py
control-plane/api/app_automation/vendor_adapters.py
control-plane/api/app_automation/executor.py
```

`adapter_base.py` defines the normalized health/result contract for vendor adapters. `vendor_adapters.py` declares one adapter class per selected provider. `executor.py` dispatches approved non-dry-run requests into the scaffolded adapter boundary once source is present.

## Seed app actions

The scaffold seeds actions for:

- GitHub
- Slack
- Gmail
- Google Calendar
- Google Sheets
- Notion
- Linear
- Jira
- Discord
- HubSpot
- generic web/browser tasks

## Execution ladder

Default selection order:

```text
api -> mcp -> workflow -> browser -> visual_browser -> desktop
```

Use API/MCP when the app has reliable native integration. Use workflow engines for deterministic multi-step app automations. Use browser or visual-browser automation when no stable API/MCP surface exists.

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
