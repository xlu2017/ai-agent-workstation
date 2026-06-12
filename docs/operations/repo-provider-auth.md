# Repo provider authentication

The control plane now separates **repo credentials** from **repo identity**.

- Repo provider answers: which server-side credential should Git use?
- Repo source registry answers: which owner/repo/branch/path backs each service?

The browser never receives a GitHub token.

## Providers

Supported credential provider choices:

- `personal_access_token` — legacy mode; reads `GITHUB_TOKEN`, `GITHUB_PAT`, or `PAT` from the server environment.
- `github_oauth` — GitHub browser login; stores the OAuth access token in a server-side secrets file.
- `none` — disables repo-backed freshness and update operations.

The selected provider is persisted in:

```bash
/opt/workstation/config/repo-provider.json
```

GitHub OAuth secrets are stored in:

```bash
/opt/workstation/config/repo-provider-secrets.json
```

The secrets file is written with `0600` permissions when the platform can set them.

## Repo source registry

Service-to-repository mappings are persisted separately in:

```bash
/opt/workstation/config/repo-sources.json
```

The registry stores service data such as:

```json
{
  "agent-core": {
    "enabled": true,
    "repo_provider": "github",
    "owner": "xlu2017",
    "repo": "agent-core",
    "branch": null,
    "path": "/opt/workstation/repos/agent-core"
  }
}
```

When `repo_url` is blank, the platform generates it from `repo_provider`, `owner`, and `repo`. This makes repo names editable data instead of hard-coded update logic.

## Backend endpoints

Credential provider endpoints:

```text
GET  /api/repo-provider/status
POST /api/repo-provider/select
GET  /api/repo-provider/github/login-url
GET  /api/repo-provider/github/callback
POST /api/repo-provider/github/disconnect
GET  /api/repo-provider/token-source
```

Repo source endpoints:

```text
GET  /api/repo-sources
GET  /api/repo-sources/{service_name}
PUT  /api/repo-sources/{service_name}
POST /api/repo-sources/{service_name}/reset
```

`/api/repo-provider/status` returns provider metadata and token availability, but never the token.

`/api/repo-provider/select` accepts:

```json
{
  "provider": "github_oauth"
}
```

`/api/repo-sources/{service_name}` accepts owner, repo, branch, path, enabled, and optional explicit repo URL fields.

## GitHub OAuth app configuration

Set:

```bash
GITHUB_OAUTH_CLIENT_ID=...
GITHUB_OAUTH_CLIENT_SECRET=...
```

The callback URL should be:

```text
https://<your-control-plane-host>/api/repo-provider/github/callback
```

Local development through Vite still calls the FastAPI backend on port `9877`; the UI sends an explicit redirect URI based on the current origin.

## Frontend behavior

The dashboard injects two panels near the Services panel.

The **Repo provider** panel can:

- show the active credential provider
- show whether a token is available
- select environment PAT, GitHub login, or no provider
- start GitHub login
- disconnect GitHub login
- refresh provider status

The **Repo sources** panel can:

- show each repo-backed service mapping
- edit owner/repo/branch/path data
- set an explicit repo URL override
- enable or disable repo-backed updates per service
- reset a service back to seeded defaults

## Integration with service updates

`service_updater` resolves credentials through the selected repo provider and resolves service repo identity through the repo source registry. `service_update_check` uses the same selected provider and source registry.

This means **Check Latest** and **Update Latest** no longer assume a raw personal access token or a specific hard-coded GitHub repo name.

## Security notes

- Tokens are never returned to the browser.
- The browser only sees provider status and token availability.
- OAuth state is stored server-side and validated in the callback.
- Command output remains sanitized before surfacing update/check errors.
- Selecting `none` intentionally disables repo-backed update credentials.
- Editing repo source data changes where update/check operations pull from; it does not expose credentials.
