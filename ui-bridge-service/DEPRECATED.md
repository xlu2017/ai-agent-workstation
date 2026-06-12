# Deprecated: standalone UI bridge service

`ui-bridge-service/` is deprecated without migration.

This folder contains a Phase 1 standalone source-resolution server. It was useful as a prototype, but it is not the product control surface and must not be used as the authority for browser context, source resolution, session routing, or agent context injection.

## Replacement direction

Use control-plane-owned routes and services:

```text
control-plane/api/routes/ui_capabilities.py
control-plane/api/routes/visual_automation.py
control-plane/api/routes/multi_frontend.py
control-plane/api/routes/session_graph/
```

The control plane must own capability gating, authorization, session identity, event storage, and any bridge between browser observations and agent context.

## Rules

1. Do not add new endpoints here.
2. Do not run this as a deployment service.
3. Do not route new browser or editor integrations through this folder.
4. If source-resolution logic is useful, move it into a tested control-plane module with graph-session identity.

See `docs/deprecated-top-level-folders.md` for the full policy.
