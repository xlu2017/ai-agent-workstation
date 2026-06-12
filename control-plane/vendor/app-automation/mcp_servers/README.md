# MCP reference servers vendor placeholder

Upstream:

```text
https://github.com/modelcontextprotocol/servers.git
```

Target source directory:

```text
control-plane/vendor/app-automation/mcp_servers/source
```

Devin/vendor task:

```bash
git clone --depth 1 https://github.com/modelcontextprotocol/servers.git control-plane/vendor/app-automation/mcp_servers/source
cat > control-plane/vendor/app-automation/mcp_servers/source/VENDORED_PATCHES.md <<'EOF'
# Vendored patches: MCP reference servers

Document local platform patches here.
EOF
```

Reason selected: reference MCP server implementations and protocol examples for filesystem, git, GitHub, Postgres, browser, and other tool surfaces.

Before committing vendored source, review upstream license files and remove generated artifacts and dependencies.
