# Vendored Runtime Dependencies

This directory is for source dependencies required to rebuild the workstation
without relying on public package/image availability at runtime. Vendored trees
in this repository are tracked by git intentionally (see `.gitignore`).

## Layout

| Path | Status | Contents |
|------|--------|----------|
| `vendor/openhands-sdk/` | Committed | Upstream [OpenHands software-agent-sdk](https://github.com/OpenHands/software-agent-sdk) source (agent-server 1.24.0). Read by the control plane for SDK contracts. |
| `vendor/openhands/` | Not populated | Optional full [OpenHands](https://github.com/OpenHands/OpenHands) runtime checkout used to build the local runtime image. |

Additional vendored provider stacks live under `control-plane/vendor/` and are
described by `control-plane/vendor/*/manifest.json`.

## OpenHands runtime image

Populate the optional runtime checkout with:

```bash
scripts/vendor-openhands.sh
```

Then build the local runtime image with:

```bash
scripts/build-openhands-local.sh
```

The checked-out commit is recorded in `config/openhands.lock.json` by
`vendor-openhands.sh` (`commit_sha` is null until the script resolves it). Do
not rely on `ghcr.io/all-hands-ai/openhands:latest` for production execution.

`vendor/openhands/` is a large upstream source tree; if you populate it, keep
it backed up separately or mirrored in a private repository/registry.
