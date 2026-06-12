# Deprecated top-level folders

The repository now treats `control-plane/` as the product control-plane surface and `scripts/`, `config/`, `ops/`, `docs/`, `rfcs/`, `knowledge/`, `bench-scripts/`, `bench-tasks/`, and `bench-results/` as active supporting surfaces.

The following top-level folders are deprecated without migration:

| Folder | Status | Replacement |
| --- | --- | --- |
| `glue/` | Deprecated legacy glue layer. A coverage audit now exists at `glue/DEPRECATION-AUDIT.md`; active control-plane replacements cover useful browser/editor/terminal ambient-context behavior. Remaining glue-only items are stale setup/demo code or intentionally unsupported direct `session.json` lifecycle behavior. | `control-plane/api`, `/api/session-graph`, `/api/sessions/{id}/ambient/*`, `/api/visual-automation/*`, `/api/app-automation/*`, `control-plane/extension`, and session graph events/projections. |
| `demo/` | Deprecated legacy demonstration scripts. The scripts hard-code old `/opt/workstation/glue` paths, direct `session.json` objects, and old bridge endpoints. | Control-plane tests, session graph fixtures, and benchmark tasks. |
| `browser-extension/` | Deprecated standalone Chrome extension prototype. It still points at the old UI bridge service and must not be extended in place. | Future browser integration should be installed, versioned, and configured through the control plane. |
| `ui-bridge-service/` | Deprecated standalone source-resolution server. It is a Phase 1 stub and must not be used as a product authority. | Control-plane UI/context, visual automation, and multi-frontend routes. |

## Deprecation rules

1. Do not add new product behavior to deprecated folders.
2. Do not start services from deprecated folders in setup scripts or deployment docs.
3. Do not create new dependencies on `/opt/workstation/glue`, direct `session.json` storage, or the standalone port `9876` bridge.
4. If useful code exists in a deprecated folder, copy the intent into an active control-plane module, add tests there, then leave a short note in the deprecated folder.
5. Do not migrate old runtime objects automatically. Legacy session objects remain deprecated without migration.

## Rationale

The old glue stack predates the current session graph and control-plane architecture. It duplicates session lifecycle, bridge routing, and context handling while relying on stale filesystem locations and old endpoints. Keeping it at the repository root without a visible deprecation marker makes future agents likely to extend the wrong surface.
