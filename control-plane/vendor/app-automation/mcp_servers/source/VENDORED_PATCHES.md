# Vendored patches

Upstream source was vendored into this repository so platform-specific revisions can be made directly.

## Import commit

- Upstream: https://github.com/modelcontextprotocol/servers.git
- Imported at: 2026-06-13T00:43:37Z
- Import method: shallow HTTPS clone
- Notes: Vendored as-is; node_modules, dist, build, .venv, caches, and .env files removed.

## Local patches

### 2026-06-13 — Add Jubilant Goggles local contract adapter

Reason:
Provide an in-tree MCP adapter boundary so the control-plane can dispatch MCP-routed actions end-to-end and compare platform-owned GitHub execution against the vendored protocol/tool surface.

Files changed:
- `jubilant_goggles_adapter.py`

Behavior changed:
- Accepts normalized action envelopes on stdin.
- Returns a normalized `adapter_contract_completed` result for supported MCP/GitHub actions when used as a local contract fallback.
- Does not call external APIs or perform side effects.
- The platform runtime still performs live `github.search_repo` and approved `github.create_issue` through server-side GitHub auth.

Tests run:
- Not run in this patching environment. Expected: `cd control-plane && pytest tests/test_app_automation.py -q`.

Known upstream divergence:
- This adapter is product-specific glue intentionally maintained inside the vendored source tree.

Template:

### YYYY-MM-DD — short title

Reason:
Files changed:
Behavior changed:
Tests run:
Known upstream divergence:
