# Repo-backed service updates

The dashboard's **Update latest** action updates allowlisted services from GitHub on the server. The browser never receives a GitHub token.

## Supported services

The service updater currently supports:

- `agent-core`
- `dashboard`
- `control-plane`

Service metadata is exposed through `GET /api/services`.

## Token configuration

Set one of:

```bash
GITHUB_TOKEN=...
GITHUB_PAT=...
PAT=...
```

If no token is available, repo-backed services remain visible but update buttons are disabled by the service metadata returned from the API. The read-only check endpoint returns `token_missing` so the UI can explain why freshness cannot be checked.

## Branch behavior

By default, the updater resolves the remote default branch with:

```bash
git ls-remote --symref <repo-url> HEAD
```

A service can override the branch with environment variables:

```bash
AGENT_CORE_UPDATE_BRANCH=main
JUBILANT_GOGGLES_UPDATE_BRANCH=main
```

## Repo and path overrides

Defaults:

```bash
AGENT_CORE_REPO_URL=https://github.com/xlu2017/agent-core.git
JUBILANT_GOGGLES_REPO_URL=https://github.com/xlu2017/jubilant-goggles.git
AGENT_CORE_REPO_PATH=/opt/workstation/repos/agent-core
JUBILANT_GOGGLES_REPO_PATH=/opt/workstation/repos/jubilant-goggles
```

Each can be overridden through the matching environment variable.

## Check Latest sequence

`GET /api/v2/services/{service}/update-check` is read-only. It does not run `git fetch`, `git reset`, install, build, or restart commands.

The check flow is:

1. Resolve the service allowlist entry.
2. Read the GitHub token from server environment.
3. Resolve the branch or remote default branch.
4. Read the remote branch commit with `git ls-remote`.
5. Acquire the same per-repo-path lock used by updates.
6. Read the local checkout commit if the checkout exists.
7. Return a structured status.

Returned statuses include:

- `up_to_date`
- `update_available`
- `missing_checkout`
- `invalid_checkout`
- `token_missing`
- `branch_resolve_failed`
- `remote_check_failed`
- `local_commit_missing`
- `update_locked`

The UI adds a **Check** button beside **Update Latest** for repo-backed services. This button calls the read-only endpoint and displays whether an update is available before the user mutates the service.

## Update sequence

For an existing checkout:

1. Resolve branch.
2. Acquire a per-repo-path lock.
3. Read current commit.
4. Fetch remote branch with the transient tokenized URL.
5. Reset hard to `FETCH_HEAD`.
6. Run service install commands.
7. Run service build commands.
8. Restart service when requested.
9. Persist status to `/opt/workstation/logs/service-updates.json`.

For a missing checkout, the updater clones the repo and then runs the same install/build/restart sequence.

## Self-update behavior

`dashboard` and `control-plane` share the `jubilant-goggles` checkout. Updating that checkout can cause uvicorn `--reload` to restart the running API before the HTTP response completes.

To avoid a browser-side network error, self-updates are deferred to a background thread. The API returns immediately, persists `in_progress`, and the UI polls `GET /api/services` until `last_update` is available.

## Status persistence

Update status is persisted at:

```bash
/opt/workstation/logs/service-updates.json
```

This survives control-plane reloads and lets the UI show the final result after a self-update.

## UI behavior

The UI update button is enhanced by `service-update-enhancer.ts`:

- injects a Check button next to repo-backed Update Latest buttons
- calls `GET /api/v2/services/{service}/update-check` for read-only freshness checks
- intercepts Update Latest button clicks before the older inline handler
- calls `POST /api/v2/services/{service}/update-latest`
- shows in-progress status
- polls `GET /api/services` for deferred updates
- displays final success or failure message
- does not expose tokens

## Failure modes

Structured errors include:

- `UNKNOWN_SERVICE`
- `NO_TOKEN`
- `BRANCH_RESOLVE_FAILED`
- `REMOTE_CHECK_FAILED`
- `UPDATE_LOCKED`
- `CLONE_FAILED`
- `NOT_A_REPO`
- `FETCH_FAILED`
- `RESET_FAILED`
- `INSTALL_FAILED`
- `BUILD_FAILED`
- `TIMEOUT`
- `UPDATE_FAILED`

Command output is sanitized before returning to the UI.
