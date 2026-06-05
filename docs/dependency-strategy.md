# Dependency Strategy: Vendoring, Mirroring, and Offline Artifacts

This document records the platform dependency policy and the rationale behind it.

## Decision

Do not treat every open-source dependency the same.

Use dependency maturity, edit frequency, and coupling to decide where each dependency belongs:

```text
actively patched / high-coupling dependencies
  -> vendor into the main platform repo

stable runtime services
  -> mirror or fork externally, pin exact commits, build local images

large binary/runtime artifacts
  -> store in an artifact registry or offline bundle, not in git
```

Current classification:

| Dependency | Role | Expected edit frequency | Strategy |
|---|---|---:|---|
| OpenHands | canonical agent runtime | high | vendor in main repo or maintain as a very close active fork |
| LiteLLM | model gateway | low to medium | mirror/fork externally, pin, build local image |
| Hatchet | durable queue/workflow runtime | low | mirror/fork externally, pin, build local image |
| Python/npm/apt deps | package dependencies | low | lock and cache in artifact store |
| Docker images | runtime artifacts | low | private registry or image tar bundle |

## Why maturity matters

The relevant factor is not maturity as a label. The practical factors are:

```text
how often we expect to edit the dependency
how unstable the dependency's integration API is
how tightly the dependency co-evolves with the platform
whether a platform feature needs coordinated changes across both codebases
```

OpenHands is the canonical execution runtime and has a large integration surface with this platform:

```text
conversation API
event stream
workspace/session mapping
tool metadata
pause/resume behavior
reason/rationale exposure
browser/runtime behavior
skills/hooks/policies
status reporting
```

Because those surfaces may need platform-specific patches, keeping OpenHands close to the platform is rational. It allows atomic changes where the platform UI, adapter, tests, and OpenHands runtime patch land together.

LiteLLM and Hatchet are different. They are important, but their roles are narrower and more stable:

```text
LiteLLM
  OpenAI-compatible model gateway
  model routing
  provider abstraction

Hatchet
  queue/workflow execution
  worker concurrency
  run history
```

The platform should rarely need to change their internals. For them, source mirroring plus exact commit pins gives resilience without bloating the main development tree.

## Repository policy

The main platform repo should contain:

```text
platform source
OpenHands adapter
session UI/control plane
vendored OpenHands if actively patched
lock files
patch files
build and restore scripts
integration tests
```

The main platform repo should not normally contain:

```text
Docker image tarballs
node_modules
Python virtualenvs
apt package caches
wheelhouse archives
npm/pnpm/yarn package caches
large build outputs
```

Those belong in an artifact store, private registry, or offline restore bundle.

## Recommended layout

```text
jubilant-goggles/
  platform code
  vendor/openhands/                 # only if actively patched with the platform
  config/dependency-locks
  scripts/build and restore tooling
  docs/dependency strategy

jubilant-goggles-vendor/openhands
  optional external active fork or mirror

jubilant-goggles-vendor/litellm
  stable source mirror or fork

jubilant-goggles-vendor/hatchet
  stable source mirror or fork

artifact store / private registry
  openhands image by commit
  litellm image by commit
  hatchet image by commit
  wheelhouse
  npm cache
  apt cache
  base images
```

## Fork versus mirror versus vendor

A fork is best when we expect to patch a dependency and possibly send changes upstream.

A mirror is best when we need supply-chain resilience and exact source retention without frequent local edits.

Vendoring is best when a dependency must co-evolve with the platform and atomic cross-codebase commits are valuable.

```text
fork
  separate repo
  preserves upstream relationship
  good for collaboration and patches

mirror
  controlled copy
  good for resilience and pinning

vendor
  copied into this repo
  good for single-repo co-development
  expensive for repo size and review noise
```

## Offline policy

Offline resilience has layers.

```text
Layer 1: reproducible from public internet
  exact commits, image digests, lock files

Layer 2: reproducible from private mirrors
  private source mirrors, private image registry, package mirrors

Layer 3: fully restorable from offline bundle
  source snapshots, image tarballs, package caches, checksums, restore script
```

The target for this platform is:

```text
OpenHands
  close vendor or active fork because it may be modified frequently

LiteLLM and Hatchet
  private mirrors or forks, exact commit pins, local images

Runtime artifacts
  private registry or offline bundle, not git
```

## Practical rule

Vendor code only when we expect to edit it or when atomic changes with the platform are valuable.

Mirror and pin code when we need resilience but do not expect frequent edits.

Archive artifacts outside git when they are large, generated, or binary.

This gives the platform supply-chain resilience without turning the main repo into an unmanageable dependency archive.
