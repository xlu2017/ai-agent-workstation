# OpenHands Runtime Architecture

OpenHands is the canonical execution runtime for the platform. The runtime should
be local, pinned, and rebuildable without relying on a floating public image.

## Architecture

```text
control plane
  -> OpenHandsExecutorAdapter
  -> OPENHANDS_URL, default http://localhost:3000
  -> local OpenHands container
  -> local image built from vendor/openhands
  -> source recorded in config/openhands.lock.json
```

Production execution must not depend on `ghcr.io/all-hands-ai/openhands:latest`.

## Files

```text
config/openhands.lock.json
vendor/README.md
vendor/openhands/
scripts/vendor-openhands.sh
scripts/build-openhands-local.sh
scripts/verify-openhands-runtime.sh
```

`vendor/openhands/` is intentionally not committed because the upstream source
tree is large. Keep it backed up separately or mirrored in a private repository.

## Setup flow

```bash
scripts/vendor-openhands.sh
scripts/build-openhands-local.sh
docker compose up -d openhands
scripts/verify-openhands-runtime.sh
```

The vendoring script records the exact OpenHands commit in
`config/openhands.lock.json`. The build script creates a local Docker image using
that vendored source. Compose then runs the local image by default.

## Pinning policy

For production, set `OPENHANDS_REF` to an exact tag or commit before vendoring.
Then commit the updated lock file and build the local image.

The platform should fail loudly if the vendored source or local image is missing.
That is intentional. Silent fallback to a public latest image makes the runtime
non-reproducible.

## Disaster recovery

For stronger resilience, mirror the built image to a private registry and keep a
backup of `vendor/openhands` plus `config/openhands.lock.json`.

This makes the platform resilient if public OpenHands GitHub or public image
hosting becomes unavailable after you have vendored and built the runtime.
