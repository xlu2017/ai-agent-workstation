# Deprecated: standalone browser extension prototype

`browser-extension/` is deprecated without migration.

This folder contains the old standalone MV3 prototype for UI-to-code selection. It still assumes the deprecated standalone UI bridge service and must not be extended in place.

## Replacement direction

Future browser integration should be owned by the control plane:

```text
control-plane/api/routes/ui_capabilities.py
control-plane/api/routes/visual_automation.py
control-plane/api/routes/multi_frontend.py
control-plane/web/
```

A future extension may still exist, but it must be installed, versioned, configured, and capability-gated by the control plane rather than maintained as an unowned top-level prototype.

## Rules

1. Do not add new behavior here.
2. Do not point setup docs at this folder.
3. Do not keep using the standalone `ui-bridge-service/` contract.
4. If a browser-extension feature is still needed, move the contract into the control plane first and add tests there.

See `docs/deprecated-top-level-folders.md` for the full policy.
