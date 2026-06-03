# Future Work

## Short-Term (Next Sprint)

### 1. Production Source Map Support
Currently limited to dev mode (React fibers/debug metadata). Add:
- Parse `.map` files from build output
- Support Vite `--sourcemap` builds
- Source map URL resolution via Chrome DevTools Protocol

### 2. Extension Polish
- Keyboard shortcut (e.g., Ctrl+Shift+I) for quick inspect
- Visual indicator showing resolution confidence
- History panel showing recent inspections
- Support for Shadow DOM elements

### 3. Session Auto-Detection
Instead of port-based routing, detect the active session by:
- Matching the URL to known worktree dev servers
- Reading a `.ui-bridge-session` file in the project root
- Using Chrome tab groups as session indicators

### 4. Event Streaming
- WebSocket connection from extension to bridge for real-time updates
- Server-Sent Events (SSE) for agent notifications
- File watcher trigger for OpenHands integration

## Medium-Term (1-3 Months)

### 5. Deep OpenHands Integration
- Custom microagent that reads UI context automatically
- API-based context injection into active conversations
- Bidirectional: agent can request "show me element X" and highlight it in browser

### 6. Multi-Framework Testing
- Vue test app validation
- Svelte test app validation
- Next.js (with server components) testing
- Edge cases: portals, suspense boundaries, error boundaries

### 7. Visual Diff Generation
- Screenshot the inspected element
- Compare before/after for UI changes
- Include visual context in agent prompt

### 8. IDE Integration
- VS Code extension that reads UI context
- Jump-to-source from context file
- Bi-directional: select in IDE → highlight in browser

## Long-Term (3-6 Months)

### 9. Multi-Agent Scheduler Integration (RFC-001)
- Automatic task creation from UI inspections
- Route "fix this button" to the agent working on that component
- Priority assignment based on user interaction patterns

### 10. React Native / Flutter Support (RFC-003, RFC-004)
- Element inspection in mobile simulators
- Metro/Flutter VM service integration
- ADB-based element hierarchy capture

### 11. AI-Powered Source Resolution
- When element-source can't resolve, use LLM to guess the source file
- Embed codebase and match element patterns to components
- Learn from corrections over time

### 12. Collaborative Multi-User
- Multiple users inspecting elements simultaneously
- Conflict resolution when two users target the same component
- Shared session dashboards

## Non-Goals

- Full IDE replacement (VS Code Remote SSH is sufficient)
- Production monitoring (use standard observability tools)
- End-user testing automation (use Playwright/Cypress instead)
- Cross-machine distributed architecture (single server is sufficient for now)
