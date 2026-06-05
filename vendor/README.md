# Vendored Runtime Dependencies

This directory is for source dependencies required to rebuild the workstation
without relying on public package/image availability at runtime.

## OpenHands

The platform should use `vendor/openhands` as the source of truth for the
OpenHands runtime.

Populate it with:

```bash
scripts/vendor-openhands.sh
```

Then build the local runtime image with:

```bash
scripts/build-openhands-local.sh
```

The checked-out commit is recorded in `config/openhands.lock.json`. Do not rely
on `ghcr.io/all-hands-ai/openhands:latest` for production execution.

The `vendor/openhands` directory is intentionally ignored by git because it is a
large upstream source tree. Keep it backed up separately or mirror it in a
private repository/registry.
