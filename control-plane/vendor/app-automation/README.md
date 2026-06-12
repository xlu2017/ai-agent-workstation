# App automation vendor workspace

This directory is the in-repo home for third-party app automation runtimes.

The platform intentionally separates:

1. **Vendored source** — patched third-party code under `control-plane/vendor/app-automation/<tool>/source`.
2. **Adapters** — platform-owned code under `control-plane/api/app_automation` that normalizes actions, risk, auth, events, and results.
3. **Policy** — approval and execution gates owned by the control plane before any app/API/GUI operation runs.

## Selected vendor stack

The manifest is `manifest.json` and currently selects:

- Activepieces — workflow engine, MCP-capable pieces, human-in-the-loop automation.
- Composio — broad API toolkit/auth bridge for app actions.
- Model Context Protocol reference servers — protocol/reference MCP implementation catalog.
- n8n — deterministic workflow engine with large integration surface. License review required.
- Stagehand — TypeScript browser-agent SDK.
- Browser Use — Python browser-agent runtime.
- Skyvern — vision/browser workflow runtime. AGPL review required.

## Vendoring policy

Run:

```bash
python3 control-plane/scripts/vendor_app_automation_tools.py --manifest control-plane/vendor/app-automation/manifest.json
```

This clones or refreshes each selected upstream repository into its `target_dir`.

After vendoring, revisions should happen directly in the checked-in source tree for tools where the license and operational policy allow it. Keep local patches documented in each tool's `VENDORED_PATCHES.md` file.

## Do not expose credentials

Vendor runtimes must never receive raw browser-visible credentials. All credentials must flow through server-owned provider/auth registries and be passed only to the final execution process.
