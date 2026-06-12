# Deprecated: legacy demo scripts

`demo/` is deprecated without migration.

The scripts in this folder were early validation demos for multi-session isolation and UI-context routing. They hard-code legacy runtime locations and old bridge endpoints, including `/opt/workstation/glue`, direct `session.json` files, and the standalone port `9876` bridge.

## Replacement direction

Use active validation surfaces instead:

```text
control-plane/tests/
bench-scripts/
bench-tasks/
docs/deprecated-top-level-folders.md
```

New demonstrations should be expressed as tests, benchmark tasks, or documented control-plane workflows. They must use the session graph API and control-plane routes rather than writing legacy session metadata directly.

## Rules

1. Do not add new demos here.
2. Do not use these scripts as setup or verification authority.
3. Do not add new hard-coded server paths, ports, or session JSON writes.
4. Convert any still-useful workflow into a control-plane test or benchmark before extending it.

See `docs/deprecated-top-level-folders.md` for the full policy.
