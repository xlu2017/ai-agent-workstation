# Deprecated: Workstation Glue Layer

`glue/` is deprecated without migration.

This folder is retained only as historical reference for the old standalone glue stack. Do not add new product behavior here, do not start services from this folder, and do not create new dependencies on `/opt/workstation/glue`.

## Replacement surface

Use the active control-plane modules instead:

```text
control-plane/api/              FastAPI routes and product contracts
control-plane/web/              dashboard and session UI
control-plane/cli/              platformctl command surface
/api/session-graph              canonical session identity and topology
control-plane/api/routes/*      UI, visual automation, services, repo, and graph routes
```

## Why this is deprecated

The old glue layer predates the session graph architecture. It duplicates session lifecycle and UI-context routing, relies on direct `session.json` objects, and assumes old paths and services such as:

```text
/opt/workstation/glue
/opt/workstation/sessions/<session-id>/session.json
/opt/workstation/sessions/<session-id>/context/latest-ui-context.md
```

Those runtime objects are not migrated. New product code must use graph-addressable sessions and control-plane routes.

## Allowed changes in this folder

Allowed:

1. Documentation that explains the deprecation.
2. Notes that point to a copied or rewritten control-plane replacement.
3. Removal after callers have been verified absent.

Not allowed:

1. New feature work.
2. New deployment or setup instructions.
3. New code that writes legacy session metadata.
4. New browser, editor, or automation integrations.

See `docs/deprecated-top-level-folders.md` and `docs/deprecated-legacy-sessions.md` for the governing policy.
