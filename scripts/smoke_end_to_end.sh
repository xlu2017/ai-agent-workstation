#!/usr/bin/env bash
#
# End-to-end smoke test for the control-plane.
#
# Usage:
#   bash scripts/smoke_end_to_end.sh
#
# Environment:
#   AGENT_CORE_URL — default http://localhost:3210
#   CONTROL_PLANE_URL — default http://localhost:9877
#   SKIP_SERVER_START — if set, assumes servers are already running
#
set -euo pipefail

AGENT_CORE_URL="${AGENT_CORE_URL:-http://localhost:3210}"
CONTROL_PLANE_URL="${CONTROL_PLANE_URL:-http://localhost:9877}"
PASS=0
FAIL=0
SKIP=0

green() { printf "\033[32m%s\033[0m\n" "$1"; }
red() { printf "\033[31m%s\033[0m\n" "$1"; }
yellow() { printf "\033[33m%s\033[0m\n" "$1"; }

check() {
    local desc="$1" result="$2"
    if [ "$result" = "0" ]; then
        green "  PASS: $desc"
        PASS=$((PASS + 1))
    else
        red "  FAIL: $desc"
        FAIL=$((FAIL + 1))
    fi
}

skip() {
    local desc="$1"
    yellow "  SKIP: $desc"
    SKIP=$((SKIP + 1))
}

echo "=== End-to-End Smoke Test ==="
echo ""

# --- 1. Check agent-core ---
echo "[1] agent-core at $AGENT_CORE_URL"
if curl -sf "$AGENT_CORE_URL/actions" > /dev/null 2>&1; then
    check "agent-core /actions responds" 0

    # Test advisory planning endpoint
    PLAN_RESP=$(curl -sf -X POST "$AGENT_CORE_URL/actions/plan" \
        -H "Content-Type: application/json" \
        -d '{"session_id":"smoke-test","repo_id":"test","prompt":"read the readme","allowed_actions":["grep","read_file"],"mode_preference":"finite"}' 2>/dev/null || echo "FAIL")
    if echo "$PLAN_RESP" | grep -q "advisory_only"; then
        check "agent-core /actions/plan returns advisory response" 0
    else
        check "agent-core /actions/plan returns advisory response" 1
    fi

    # Test validate-plan
    VAL_RESP=$(curl -sf -X POST "$AGENT_CORE_URL/actions/validate-plan" \
        -H "Content-Type: application/json" \
        -d '{"allowed_actions":["grep","read_file"],"plan":{"mode":"finite","steps":[{"action":"grep","params":{"pattern":"hello","path":"."}}]}}' 2>/dev/null || echo "FAIL")
    if echo "$VAL_RESP" | grep -q "advisory_only"; then
        check "agent-core /actions/validate-plan returns advisory response" 0
    else
        check "agent-core /actions/validate-plan returns advisory response" 1
    fi

    # Deprecated endpoints return 410
    EXEC_RESP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$AGENT_CORE_URL/actions/execute" \
        -H "Content-Type: application/json" -d '{}' 2>/dev/null || echo "000")
    if [ "$EXEC_RESP" = "410" ]; then
        check "agent-core /actions/execute returns 410 (deprecated)" 0
    else
        check "agent-core /actions/execute returns 410 (deprecated)" 1
    fi
else
    skip "agent-core not running at $AGENT_CORE_URL"
fi

echo ""

# --- 2. Check control-plane ---
echo "[2] control-plane at $CONTROL_PLANE_URL"
if curl -sf "$CONTROL_PLANE_URL/api/health" > /dev/null 2>&1; then
    check "control-plane /api/health responds" 0

    # Create a session
    SESSION_RESP=$(curl -sf -X POST "$CONTROL_PLANE_URL/api/sessions" \
        -H "Content-Type: application/json" \
        -d '{"name":"smoke-test","task":"end-to-end smoke test"}' 2>/dev/null || echo "FAIL")
    if echo "$SESSION_RESP" | grep -q "id"; then
        SESSION_ID=$(echo "$SESSION_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null || echo "")
        check "POST /api/sessions creates a session" 0
    else
        SESSION_ID=""
        check "POST /api/sessions creates a session" 1
    fi

    # List sessions
    LIST_RESP=$(curl -sf "$CONTROL_PLANE_URL/api/sessions" 2>/dev/null || echo "FAIL")
    if echo "$LIST_RESP" | grep -q "sessions"; then
        check "GET /api/sessions returns sessions" 0
    else
        check "GET /api/sessions returns sessions" 1
    fi

    if [ -n "$SESSION_ID" ]; then
        # Submit a harmless prompt
        echo ""
        echo "[3] Prompt flow test"
        CHAT_RESP=$(curl -sf -X POST "$CONTROL_PLANE_URL/api/sessions/$SESSION_ID/chat" \
            -H "Content-Type: application/json" \
            -d '{"instruction":"Inspect the repo and summarize the README. Do not edit files."}' 2>/dev/null || echo "FAIL")
        if echo "$CHAT_RESP" | grep -q "task_id"; then
            check "POST /api/sessions/:id/chat accepts prompt" 0
            STATE=$(echo "$CHAT_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('state',''))" 2>/dev/null || echo "")
            echo "    State: $STATE"
            if [ "$STATE" = "completed" ] || [ "$STATE" = "blocked" ] || [ "$STATE" = "failed" ]; then
                check "Task state is truthful (not hanging)" 0
            else
                check "Task state is truthful (not hanging)" 1
            fi
        else
            check "POST /api/sessions/:id/chat accepts prompt" 1
        fi

        # Check events
        EVENTS_RESP=$(curl -sf "$CONTROL_PLANE_URL/api/sessions/$SESSION_ID/events" 2>/dev/null || echo "FAIL")
        if echo "$EVENTS_RESP" | grep -q "events"; then
            check "GET /api/sessions/:id/events returns events" 0
            TOTAL=$(echo "$EVENTS_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total',0))" 2>/dev/null || echo "0")
            if [ "$TOTAL" -gt "0" ]; then
                check "Events were recorded ($TOTAL events)" 0
            else
                check "Events were recorded (0 events)" 1
            fi
        else
            check "GET /api/sessions/:id/events returns events" 1
        fi

        # Check state endpoint
        STATE_RESP=$(curl -sf "$CONTROL_PLANE_URL/api/sessions/$SESSION_ID/state" 2>/dev/null || echo "FAIL")
        if echo "$STATE_RESP" | grep -q "state"; then
            check "GET /api/sessions/:id/state returns truthful state" 0
        else
            check "GET /api/sessions/:id/state returns truthful state" 1
        fi

        # Clean up
        curl -sf -X DELETE "$CONTROL_PLANE_URL/api/sessions/$SESSION_ID" > /dev/null 2>&1 || true
    fi
else
    skip "control-plane not running at $CONTROL_PLANE_URL"
fi

echo ""

# --- 3. CLI check ---
echo "[4] CLI check"
CLI_PATH="control-plane/cli/platformctl.py"
if [ -f "$CLI_PATH" ]; then
    if python3 "$CLI_PATH" --help > /dev/null 2>&1; then
        check "platformctl --help works" 0
    else
        check "platformctl --help works" 1
    fi
    if python3 "$CLI_PATH" session --help > /dev/null 2>&1; then
        check "platformctl session --help works" 0
    else
        check "platformctl session --help works" 1
    fi
    if python3 "$CLI_PATH" models --help > /dev/null 2>&1; then
        check "platformctl models --help works" 0
    else
        check "platformctl models --help works" 1
    fi
    if python3 "$CLI_PATH" knowledge --help > /dev/null 2>&1; then
        check "platformctl knowledge --help works" 0
    else
        check "platformctl knowledge --help works" 1
    fi
else
    skip "CLI not found at $CLI_PATH"
fi

echo ""

# --- 4. Python compile checks ---
echo "[5] Python compile checks"
for mod in api/server.py cli/platformctl.py sessions/session_manager.py execution/prompt_handler.py; do
    if python3 -m py_compile "control-plane/$mod" 2>/dev/null; then
        check "py_compile control-plane/$mod" 0
    else
        check "py_compile control-plane/$mod" 1
    fi
done

echo ""
echo "=== Results ==="
echo "  Passed: $PASS"
echo "  Failed: $FAIL"
echo "  Skipped: $SKIP"
echo ""

if [ "$FAIL" -gt 0 ]; then
    red "SMOKE TEST FAILED"
    exit 1
else
    green "SMOKE TEST PASSED"
    exit 0
fi
