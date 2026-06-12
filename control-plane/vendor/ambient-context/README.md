# Ambient context vendor stack

Vendored upstream provider libraries for ambient-context observation.

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
| python-lsp-server | Python editor symbols and diagnostics | editor_bridge, python_diagnostics, symbol_lookup |
| source-map | JavaScript source-map reference | source_mapping, dom_to_source |

## Fetching vendor source

Do not clone with SSH. Use the server-side ambient vendor API or script.

```bash
python3 control-plane/scripts/vendor_ambient_context_tools.py --all
python3 control-plane/scripts/vendor_ambient_context_tools.py --tool playwright_python
```

Auth is read server-side through the repo provider auth layer or `GITHUB_TOKEN`/`GITHUB_PAT` environment variables.

## License review

Before redistributing vendored source, review each upstream project's license.
