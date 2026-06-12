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

## Vendoring instructions for Devin

The GitHub connector used by ChatGPT cannot clone entire upstream repositories into this repository. Devin should run:

```bash
python3 control-plane/scripts/vendor_app_automation_tools.py --manifest control-plane/vendor/app-automation/manifest.json
```

Or clone individual tools:

```bash
python3 control-plane/scripts/vendor_app_automation_tools.py --tool activepieces
python3 control-plane/scripts/vendor_app_automation_tools.py --tool composio
python3 control-plane/scripts/vendor_app_automation_tools.py --tool mcp_servers
python3 control-plane/scripts/vendor_app_automation_tools.py --tool n8n
python3 control-plane/scripts/vendor_app_automation_tools.py --tool stagehand
python3 control-plane/scripts/vendor_app_automation_tools.py --tool browser_use
python3 control-plane/scripts/vendor_app_automation_tools.py --tool skyvern
```

Each tool has a placeholder README under:

```text
control-plane/vendor/app-automation/<tool>/README.md
```

The actual vendored source should go into:

```text
control-plane/vendor/app-automation/<tool>/source
```

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

The current execute endpoint is deliberately conservative. It performs:

1. action lookup
2. vendor selection
3. risk classification
4. approval gate
5. dry-run plan
6. vendor install check

Concrete runtime invocation is blocked until vendored source is present and adapter-specific execution is reviewed.

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

Before vendoring and redistributing source, review the upstream license for each selected tool. n8n and Skyvern require special attention because their licenses may impose obligations that differ from permissive MIT/Apache-style libraries.
