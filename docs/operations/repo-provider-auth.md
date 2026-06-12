# Repo provider authentication

The control plane now has a repo provider layer for Git-backed service operations. It lets the UI choose whether **Check Latest** and **Update Latest** use a server environment personal access token or a GitHub OAuth login.

The browser never receives either token.

## Providers

Supported provider choices:

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

## Backend endpoints

```text
GET  /api/repo-provider/status
POST /api/repo-provider/select
GET  /api/repo-provider/github/login-url
GET  /api/repo-provider/github/callback
POST /api/repo-provider/github/disconnect
GET  /api/repo-provider/token-source
```

`/status` returns provider metadata and token availability, but never the token.

`/select` accepts:

```json
{
  "provider": "github_oauth"
}
```

`/github/login-url` creates an OAuth state value, persists it server-side, and returns the GitHub authorization URL.

`/github/callback` validates state, exchanges the code for an access token, stores it server-side, switches the active provider to `github_oauth`, and redirects the browser back to the dashboard.

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

The dashboard injects a **Repo provider** panel near the Services panel. It can:

- show the active provider
- show whether a token is available
- select environment PAT, GitHub login, or no provider
- start GitHub login
- disconnect GitHub login
- refresh provider status

## Integration with service updates

`service_updater` now resolves its credential through the selected repo provider when mounted by the API route layer. `service_update_check` directly uses the selected provider token.

This means **Check Latest** and **Update Latest** no longer need to assume a raw personal access token. The legacy environment PAT remains available as one provider option for server-only deployments.

## Security notes

- Tokens are never returned to the browser.
- The browser only sees provider status and token availability.
- OAuth state is stored server-side and validated in the callback.
- Command output remains sanitized before surfacing update/check errors.
- Selecting `none` intentionally disables repo-backed update credentials.
