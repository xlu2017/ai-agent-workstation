# Multi Frontend Validation Matrix

## UI target

The UI should render a matrix like:

```text
App: Checkout App
Backend: API healthy http://127.0.0.1:8080
Isolation: shared backend, separate user

Frontend             OS       Runtime    URL         Health   Latest trace
Chrome desktop       web      browser    /checkout   healthy  trace-web-1
Android emulator     android  emulator   /checkout   failing  trace-android-1
iOS simulator        ios      simulator  /checkout   healthy  trace-ios-1
```

## Agent context packet

When the user asks the agent to fix or compare behavior across clients, context should include:

```text
root app session id
backend session id
active frontend session id
other comparable frontend session ids
device profile
current URL
selected component or visual fallback bounds
recent frontend network requests
correlated backend traces
backend route logs or errors
source hints
```

## Agent resolution order

```text
1. selected frontend source hints
2. frontend route and component search
3. cross-client comparison traces
4. backend route or log trace
5. fallback visual evidence
6. targeted browser or emulator validation
```

## Validation runner target

A future validation runner should drive each frontend through the same user flow and compare:

```text
route reached
visible UI state
network status codes
backend trace status
console errors
accessibility status
responsive constraints
user-visible copy
```

Each run should produce one row per frontend and one aggregate result for the root app session.

## Non-goals

```text
do not merge every frontend into one browser context
do not assume all clients use the same auth state
do not require screenshots for normal operation
do not let one emulator contaminate another client state
do not treat backend logs as useful unless correlated to a frontend instance
```

## Current scaffold status

Implemented:

```text
typed models
session graph controller
trace header builder
trace registration
frontend matrix projection
unit tests for controller behavior
router file for API exposure
architecture documentation
```

Not yet implemented:

```text
server.py router mount
frontend UI matrix panel
OpenTelemetry injection middleware
emulator lifecycle manager
per-frontend ambient stream integration
coordinated multi-client workflow runner
```
