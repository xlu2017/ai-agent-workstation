# Offline Open Source Dependency Policy

The platform should be able to run from source and local artifacts without pulling
required open-source runtime dependencies from public GitHub, GHCR, PyPI, npm, or
apt at execution time.

## Required vendored source repositories

The required upstream source repositories are declared in:

```text
config/vendor-repos.json
```

Current required repos:

```text
vendor/openhands   canonical agent runtime
vendor/litellm     model gateway
vendor/hatchet     durable queue and worker runtime
```

Submodules are not sufficient. The source trees must be copied into `vendor/` as
normal tracked files so a clone of the platform repository contains the upstream
source content.

## Import source trees

Run:

```bash
scripts/vendor-source-repos.sh
```

Then commit:

```bash
git add vendor config/vendor-repos.lock.json
git commit -m "vendor: add offline open source dependencies"
```

This may create a large commit. That is intentional if the requirement is a
self-contained repository.

## Build local runtime images

Run:

```bash
scripts/build-offline-images.sh
```

This builds:

```text
localhost/openhands-platform:local
localhost/litellm-platform:local
```

`docker-compose.yml` uses those local images by default.

## Verify offline readiness

Run:

```bash
scripts/verify-offline-readiness.sh
```

The check fails if:

```text
vendor source trees are missing
vendor lock file is missing
required local Docker images are missing
floating public runtime image references remain outside vendor/
```

## Remaining external surfaces

This policy vendors the source repos and requires local runtime images. Full
air-gap operation also requires separate local mirrors for operating-system
packages, Python wheels, npm packages, Docker base images, and model provider
access or local model serving. Those artifacts are larger than source vendoring
and should be managed in `/opt/workstation/artifacts` or a private registry.
