# n8n vendor placeholder

Upstream:

```text
https://github.com/n8n-io/n8n.git
```

Target source directory:

```text
control-plane/vendor/app-automation/n8n/source
```

Devin/vendor task:

```bash
git clone --depth 1 https://github.com/n8n-io/n8n.git control-plane/vendor/app-automation/n8n/source
cat > control-plane/vendor/app-automation/n8n/source/VENDORED_PATCHES.md <<'EOF'
# Vendored patches: n8n

Document local platform patches here.
EOF
```

Reason selected: mature deterministic workflow engine with a broad integration surface, webhooks, templates, and custom code nodes.

License caution: n8n is not a simple permissive dependency. Review upstream license files before redistributing modified vendored source.

Before committing vendored source, remove generated build artifacts, caches, and dependencies such as `node_modules`.
