# Setup Guide

## Prerequisites

- Python 3.12+ (with pipx)
- Node.js 22+ (with npm)
- Chrome browser
- tmux
- git

All prerequisites are already installed on the workstation.

## Installation

### 1. Install par (session manager)

```bash
cd /opt/workstation/upstream/par
pipx install .
export PATH="$HOME/.local/bin:$PATH"
# Add to ~/.zshrc: export PATH="$HOME/.local/bin:$PATH"
```

### 2. Install bridge service dependencies

```bash
cd /opt/workstation/glue/ui-bridge
pip install -r requirements.txt --break-system-packages
# Or use a venv:
# python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```

### 3. Install glue CLI

```bash
chmod +x /opt/workstation/glue/bin/glue
ln -sf /opt/workstation/glue/bin/glue /usr/local/bin/glue
```

### 4. Build element-source for browser extension

```bash
cd /opt/workstation/upstream
# element-source provides a global build at dist/index.global.js
# If not built, get from npm:
npm pack element-source
tar xzf element-source-*.tgz
cp package/dist/index.global.js /opt/workstation/glue/browser-extension/element-source.global.js
```

Or download directly:
```bash
curl -o /opt/workstation/glue/browser-extension/element-source.global.js \
  https://unpkg.com/element-source/dist/index.global.js
```

### 5. Load browser extension

1. Open Chrome on the workstation (via RDP)
2. Navigate to `chrome://extensions`
3. Enable "Developer mode" (toggle in top right)
4. Click "Load unpacked"
5. Select `/opt/workstation/glue/browser-extension`
6. Extension should appear with "AI Agent UI Bridge" name

### 6. Install test app

```bash
cd /opt/workstation/glue/test-app
npm install
npm run dev  # Starts on port 5180
```

## Start Services

```bash
# Terminal 1: Bridge service
cd /opt/workstation/glue/ui-bridge
uvicorn server:app --host 0.0.0.0 --port 9876

# Terminal 2: Test app
cd /opt/workstation/glue/test-app
npm run dev

# Verify
curl http://localhost:9876/health
curl http://localhost:5180
```

## Verify Installation

```bash
# Check par
par --version

# Check bridge
curl -s http://localhost:9876/health | python3 -m json.tool

# Check glue CLI
glue session list

# Check extension
# Open Chrome → extension popup should show "Bridge service connected"
```
