# Browser Use vendor placeholder

Upstream:

```text
https://github.com/browser-use/browser-use.git
```

Target source directory:

```text
control-plane/vendor/app-automation/browser_use/source
```

Devin/vendor task:

```bash
git clone --depth 1 https://github.com/browser-use/browser-use.git control-plane/vendor/app-automation/browser_use/source
cat > control-plane/vendor/app-automation/browser_use/source/VENDORED_PATCHES.md <<'EOF'
# Vendored patches: Browser Use

Document local platform patches here.
EOF
```

Reason selected: Python browser-agent runtime for natural-language web task automation and browser-session execution.

Before committing vendored source, review upstream license files and remove generated build artifacts, caches, virtualenvs, and browser profile state.
