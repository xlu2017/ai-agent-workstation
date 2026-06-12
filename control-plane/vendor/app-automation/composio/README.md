# Composio vendor placeholder

Upstream:

```text
https://github.com/ComposioHQ/composio.git
```

Target source directory:

```text
control-plane/vendor/app-automation/composio/source
```

Devin/vendor task:

```bash
git clone --depth 1 https://github.com/ComposioHQ/composio.git control-plane/vendor/app-automation/composio/source
cat > control-plane/vendor/app-automation/composio/source/VENDORED_PATCHES.md <<'EOF'
# Vendored patches: Composio

Document local platform patches here.
EOF
```

Reason selected: broad agent-facing API toolkit and auth bridge for popular SaaS app actions.

Before committing vendored source, review upstream license files and remove generated build artifacts, caches, and dependencies such as `.venv`, `node_modules`, or build output.
