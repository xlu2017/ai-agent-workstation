# Ambient context vendor stack

The ambient context scaffold uses a vendored provider stack for browser, editor, terminal, repo, runtime, and desktop observation.

## Source of truth

```text
control-plane/vendor/ambient-context/manifest.json
```

## Selected tools

| Tool | Role | Collector targets |
| --- | --- | --- |
| Playwright Python | Browser CDP, DOM, accessibility, console, network | browser_cdp, dom_snapshot, accessibility_tree, console, network |
| Playwright | Upstream browser protocol reference | browser_protocol, cdp_reference, browser_automation_reference |
| Tree-sitter | Code structure, symbols, syntax | source_mapping, symbols, syntax_tree |
| watchfiles | Repo/worktree file change events | repo_watcher, file_change_events |
| pygls | Editor/LSP bridge | editor_bridge, lsp_context, diagnostics |
| pyte | Terminal screen reconstruction | terminal_collector, pty_screen_state |
| OpenTelemetry Python | Runtime tracing | runtime_trace, fastapi_asgi_tracing, request_correlation |
| python-lsp-server | Python editor symbols/diagnostics | editor_bridge, python_diagnostics, symbol_lookup |
| source-map | JavaScript source-map reference | source_mapping, dom_to_source |

## Fetching vendor source

All fetch operations use server-side GitHub authentication.  SSH is never used.

### Via API

```text
GET  /api/ambient/vendors                       — list vendor status
POST /api/ambient/vendors/{tool_id}/fetch        — fetch single tool
POST /api/ambient/vendors/fetch-all              — fetch all tools
```

### Via CLI

```bash
python3 control-plane/scripts/vendor_ambient_context_tools.py --tool playwright_python
python3 control-plane/scripts/vendor_ambient_context_tools.py --all
python3 control-plane/scripts/vendor_ambient_context_tools.py --tool pygls --ref main
python3 control-plane/scripts/vendor_ambient_context_tools.py --tool pygls --force
```

## Authentication

Credential source order:

1. `get_repo_provider_token()` from `control-plane/api/repo_provider.py`
2. `GITHUB_TOKEN` environment variable
3. `GITHUB_PAT` environment variable
4. `PAT` environment variable

If no token is available the service returns:

```json
{
  "ok": false,
  "error": {
    "code": "GITHUB_AUTH_REQUIRED",
    "message": "Configure GitHub login or GITHUB_TOKEN before fetching ambient vendors."
  }
}
```

The token is never exposed to the browser, written into logs, manifests, patch files, or generated README files.

## Fetch mechanism

The preferred fetch uses the GitHub REST API archive endpoint:

```text
GET /repos/{owner}/{repo}/zipball/{ref}
Authorization: Bearer <server-side-token>
```

The archive is extracted into the configured `target_dir`, stripping the top-level zip folder.

## Control-plane abstraction

Platform-owned code:

```text
control-plane/api/ambient_vendor/       — models, registry, github_fetcher, service
control-plane/api/routes/ambient_vendors.py — API routes
control-plane/ambient/vendor_registry.py    — manifest loader and registry
```

## Safety constraints

- Target directory must be empty (or use `force=true`) before fetching.
- Tokens are never persisted in metadata files.
- Vendored source is not imported at runtime; only metadata is read.
- First-party collectors remain platform-owned contracts.
