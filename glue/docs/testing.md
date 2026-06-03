# Testing Guide

## End-to-End Test Procedure

### Prerequisites
1. Bridge service running on :9876
2. Test app running on :5180
3. Browser extension loaded in Chrome
4. At least one session created

### Test Steps

#### Test 1: Bridge Health
```bash
curl -s http://localhost:9876/health
# Expected: {"status":"ok","service":"ui-bridge","version":"0.2.0"}
```

#### Test 2: Test App Running
```bash
curl -s http://localhost:5180 | grep "UI Bridge Test App"
# Expected: <title>UI Bridge Test App</title>
```

#### Test 3: Session Creation
```bash
glue session create test-session
glue session list
# Expected: test-session listed with ACTIVE status
```

#### Test 4: Selection Event (via curl, simulating extension)
```bash
curl -s -X POST http://localhost:9876/selection \
  -H "Content-Type: application/json" \
  -d '{
    "type": "selection",
    "session_id": "test-session",
    "url": "http://localhost:5180/",
    "selected_text": "Submit",
    "element": {"tag": "button", "id": "submit-btn", "class": "btn-primary"},
    "source": {"framework": "react", "component": "SubmitButton", "file": "src/components/SubmitButton.jsx", "line": 15, "confidence": "high"}
  }'
# Expected: {"status":"ok","event_id":"..."}
```

#### Test 5: Context File Written
```bash
cat /opt/workstation/sessions/test-session/context/latest-ui-context.md
# Expected: Markdown with element info and source resolution
```

#### Test 6: Event Log
```bash
cat /opt/workstation/sessions/test-session/context/ui-events.jsonl | python3 -m json.tool
# Expected: JSON event with all fields
```

#### Test 7: Events API
```bash
curl -s "http://localhost:9876/events?session_id=test-session" | python3 -m json.tool
# Expected: {"events": [...]}
```

#### Test 8: Browser Extension (Manual)
1. Open Chrome → http://localhost:5180
2. Click extension popup → verify "Bridge service connected"
3. Right-click "Submit" button → "Inspect element for agent"
4. Crosshair appears → click an element
5. Check: `cat /opt/workstation/sessions/session-port-5180/context/latest-ui-context.md`

### Cleanup
```bash
glue session destroy test-session
```

## Automated Smoke Test

```bash
#!/bin/bash
# smoke-test.sh — Verify glue layer end-to-end

set -e

echo "1. Bridge health..."
curl -sf http://localhost:9876/health > /dev/null && echo "  OK" || echo "  FAIL"

echo "2. Create test session..."
python3 /opt/workstation/glue/bin/glue session create smoke-test 2>/dev/null && echo "  OK" || echo "  FAIL"

echo "3. Send test event..."
curl -sf -X POST http://localhost:9876/selection \
  -H "Content-Type: application/json" \
  -d '{"type":"selection","session_id":"smoke-test","url":"http://localhost:5180/","selected_text":"Hello","element":{"tag":"h1"},"source":{"framework":"react","component":"App","file":"src/App.jsx","line":5,"confidence":"high"}}' > /dev/null && echo "  OK" || echo "  FAIL"

echo "4. Verify context file..."
test -f /opt/workstation/sessions/smoke-test/context/latest-ui-context.md && echo "  OK" || echo "  FAIL"

echo "5. Verify events log..."
test -f /opt/workstation/sessions/smoke-test/context/ui-events.jsonl && echo "  OK" || echo "  FAIL"

echo "6. Cleanup..."
python3 /opt/workstation/glue/bin/glue session destroy smoke-test 2>/dev/null && echo "  OK" || echo "  FAIL"

echo "Done."
```
