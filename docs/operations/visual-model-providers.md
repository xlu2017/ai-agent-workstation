# Visual model providers for screenshot-guided automation

This scaffold adds a control-plane boundary for providers that can reason over screenshots and textual observations, then either verify state or propose the next GUI action.

## Intent

The platform needs two distinct visual operations:

1. **Verify screen state** — decide whether an automated workflow completed, failed, is blocked, or is uncertain.
2. **Propose GUI action** — given a screenshot and context, propose the next click/type/key/scroll/drag/wait action.

These operations must not be conflated. Verification is cheaper and safer; action proposal has coordinate and side-effect risk and should be gated before execution.

## Provider stack

Supported provider IDs:

```text
anthropic_computer_use
  Default for arbitrary GUI surfaces: Guacamole, VNC, remote Linux desktop, emulators, browser windows, and native apps.

gemini_computer_use
  Preferred for browser-only workflows where the target surface is known to be a web app.

openai_computer_use
  Fallback/evaluator for high-resolution screenshot interpretation and action proposal.

plain_vision_verifier
  Verification-only path for cheaper state checks when no next GUI action is needed.
```

## Environment configuration

```bash
ANTHROPIC_API_KEY=...
ANTHROPIC_COMPUTER_USE_MODEL=claude-sonnet-4-5

GEMINI_API_KEY=...        # or GOOGLE_API_KEY=...
GEMINI_COMPUTER_USE_MODEL=gemini-2.5-computer-use-preview-10-2025

OPENAI_API_KEY=...
OPENAI_COMPUTER_USE_MODEL=computer-use-preview

VISUAL_VERIFIER_API_KEY=...
PLAIN_VISION_VERIFIER_MODEL=provider-default-vision-model
```

Provider credentials are read only on the server. The browser receives provider status but not secrets.

## API endpoints

```text
GET  /api/visual-automation/providers
POST /api/visual-automation/verify-screen
POST /api/visual-automation/propose-action
POST /api/visual-automation/normalize-action
```

The current implementation is a safe scaffold. It performs provider selection, request preview construction, dry-run planning, configuration checks, and provider-output normalization. It does not yet call live provider APIs.

## Observation packet

Both verification and action proposal accept a normalized observation packet:

```json
{
  "goal": "Verify the workflow completed and decide the next action.",
  "surface_kind": "remote_desktop",
  "screenshot": {
    "media_type": "image/png",
    "base64": "...",
    "width": 1280,
    "height": 720,
    "source": "guacamole"
  },
  "terminal_output": "pytest passed",
  "command_history": [
    {"command": "pytest -q", "exit_code": 0, "stdout": "...", "stderr": ""}
  ],
  "ui_text": "optional OCR or extracted text",
  "dom_snapshot": "optional DOM snapshot",
  "accessibility_tree": "optional accessibility tree",
  "recent_actions": [
    {"action": "clicked Submit", "result": "success dialog appeared"}
  ],
  "verification_criteria": ["success message visible"]
}
```

Screenshots, terminal output, command history, DOM snapshots, accessibility trees, and recent actions can be supplied together. The provider should use all of them as evidence.

## Verification output

`verify-screen` returns:

```text
done | not_done | blocked | uncertain
```

with evidence and missing information.

## Action proposal output

`propose-action` returns a normalized visual action:

```text
screenshot
click
double_click
right_click
type
key
scroll
drag
wait
zoom
none
```

The model provider may return provider-specific tool calls. The control plane normalizes them to platform actions before any GUI executor is allowed to run them.

## Provider routing policy

Automatic routing is:

```text
Verification:
  plain_vision_verifier if configured
  else Gemini for browser surfaces
  else Anthropic
  else OpenAI

Action proposal:
  Gemini for browser surfaces when configured
  else Anthropic
  else OpenAI
  else Gemini
```

## Execution boundary

Visual providers only propose or verify. They must not directly control the GUI.

The authoritative control plane should perform:

1. coordinate scaling from provider coordinates to real display coordinates
2. policy and approval checks
3. execution through Guacamole/VNC/Playwright/emulator/desktop bridge
4. fresh screenshot capture
5. append-only event logging
6. feedback loop back to the provider

## Next implementation steps

1. Implement provider adapters for Anthropic, Gemini, and OpenAI request/response APIs.
2. Add screenshot capture adapters for Guacamole, Playwright, emulator, and desktop/VNC surfaces.
3. Add coordinate scaling and display metadata tracking.
4. Add approval gates for actions with external side effects.
5. Persist visual observation/action events into the session event stream.
6. Add provider fallback and cross-provider verification for low-confidence actions.
