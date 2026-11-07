# demo-monorepo (taskflow) — demo fixture

A small npm-workspaces monorepo (`apps/web`, `apps/api`, `packages/shared`,
`packages/db`) used as a fixture by the legacy `demo/three-session-demo.sh`
script and early multi-session isolation checks.

Notes:

- It is a demo fixture, not a deployed service. `demo/` is a deprecated
  top-level folder; see `docs/deprecated-top-level-folders.md`.
- `docker-compose.yml` references `Dockerfile.api` and `Dockerfile.web`,
  which are intentionally not included — run the apps via npm workspaces
  (`npm run dev:web`, `npm run dev:api`) or treat the compose file as a
  sketch for containerizing the fixture.
