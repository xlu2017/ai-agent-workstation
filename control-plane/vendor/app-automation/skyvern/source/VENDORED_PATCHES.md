# Vendored patches

Upstream source was vendored into this repository so platform-specific revisions can be made directly.

## Import commit

- Upstream: https://github.com/Skyvern-AI/skyvern.git
- Imported at: 2026-06-13T00:43:37Z
- Import method: shallow HTTPS clone
- Notes: Vendored as-is; node_modules, dist, build, .venv, caches, and .env files removed.

## Local patches

### 2026-06-13 — Add Jubilant Goggles local contract adapter

Reason:
Provide an in-tree visual-browser adapter boundary so the control-plane can dispatch Skyvern-routed actions end-to-end without launching a browser during local validation.

Files changed:
- `jubilant_goggles_adapter.py`

Behavior changed:
- Accepts normalized action envelopes on stdin.
- Returns a normalized `adapter_contract_completed` result for supported visual web actions.
- Does not launch a browser or perform external side effects.
- Directs live visual-browser execution to `SKYVERN_COMMAND`.

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
