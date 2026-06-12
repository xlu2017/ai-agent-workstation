# Stagehand vendor placeholder

Upstream:

```text
https://github.com/browserbase/stagehand.git
```

Target source directory:

```text
control-plane/vendor/app-automation/stagehand/source
```

Devin/vendor task:

```bash
git clone --depth 1 https://github.com/browserbase/stagehand.git control-plane/vendor/app-automation/stagehand/source
cat > control-plane/vendor/app-automation/stagehand/source/VENDORED_PATCHES.md <<'EOF'
# Vendored patches: Stagehand

Document local platform patches here.
EOF
```

Reason selected: TypeScript browser-agent SDK for web-app workflows where deterministic API/MCP actions are unavailable.

Before committing vendored source, review upstream license files and remove generated build artifacts, caches, and dependencies such as `node_modules`.
