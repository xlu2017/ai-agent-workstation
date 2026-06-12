# Activepieces vendor placeholder

Upstream:

```text
https://github.com/activepieces/activepieces.git
```

Target source directory:

```text
control-plane/vendor/app-automation/activepieces/source
```

Devin/vendor task:

```bash
git clone --depth 1 https://github.com/activepieces/activepieces.git control-plane/vendor/app-automation/activepieces/source
cat > control-plane/vendor/app-automation/activepieces/source/VENDORED_PATCHES.md <<'EOF'
# Vendored patches: Activepieces

Document local platform patches here.
EOF
```

Reason selected: broad open-source workflow automation engine and connector/piece catalog, useful for app API workflows and MCP-facing actions.

Before committing vendored source, review upstream license files and remove generated build artifacts, caches, and dependencies such as `node_modules`.
