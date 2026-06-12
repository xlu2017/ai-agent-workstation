# Multi Frontend Shared Backend Intent

The platform should support many frontend clients connected to one backend at the same time. A client can be a desktop browser, mobile emulator, simulator, webview, or remote desktop browser.

This is not one flat browser session. It is:

```text
one root app session
one shared backend session
many isolated frontend client sessions
one correlated trace graph
```

## Topology

```text
App session
  Backend runtime session
  Frontend runtime session: Chrome desktop
  Frontend runtime session: Android emulator
  Frontend runtime session: iOS simulator
```

The root app session owns the product goal and matrix. The backend session owns API process state, logs, traces, route map, and backend health. Each frontend session owns device profile, current URL, browser or emulator identity, selected component state, and frontend observations.

## Isolation rule

Frontend state is isolated. Backend observation is shared.

Isolated per frontend:

```text
browser profile
emulator id
cookies
local storage
session storage
viewport
current URL
console logs
selected component
frontend network stream
```

Shared through the backend:

```text
backend process
base URL
route map
backend logs
trace store
source graph
repo or worktree when intentionally shared
```

Controlled sharing:

```text
auth identity
tenant id
database writes
cache state
feature flags
background jobs
```

Default mode should be one backend with separate test users per frontend. Shared users or shared tenants are allowed only when the workflow intentionally needs shared state.
