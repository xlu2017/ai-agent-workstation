# Skyvern vendor placeholder

Upstream:

```text
https://github.com/Skyvern-AI/skyvern.git
```

Target source directory:

```text
control-plane/vendor/app-automation/skyvern/source
```

Devin/vendor task:

```bash
git clone --depth 1 https://github.com/Skyvern-AI/skyvern.git control-plane/vendor/app-automation/skyvern/source
cat > control-plane/vendor/app-automation/skyvern/source/VENDORED_PATCHES.md <<'EOF'
# Vendored patches: Skyvern

Document local platform patches here.
EOF
```

Reason selected: visual browser workflow runtime for brittle websites and pages where DOM selectors are unreliable.

License caution: review upstream AGPL/commercial-license implications before redistributing modified vendored source.

Before committing vendored source, remove generated build artifacts, caches, virtualenvs, browser profiles, and screenshots containing sensitive data.
