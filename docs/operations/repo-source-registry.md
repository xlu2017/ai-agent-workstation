# Repo source registry

The repo source registry maps services to repository identity. It is separate from the repo provider credential selection.

## Intent

Repo-backed update/check behavior should not be hard-coded to a specific GitHub repository name. The service updater should ask two separate questions:

1. Which credential provider should be used?
2. Which repository source backs this service?

The repo provider layer answers the first question. The repo source registry answers the second.

## Persistence

The registry is stored at:

```bash
/opt/workstation/config/repo-sources.json
```

Override with:

```bash
REPO_SOURCE_REGISTRY_PATH=/custom/path/repo-sources.json
```

## Shape

```json
{
  "version": 1,
  "services": {
    "agent-core": {
      "enabled": true,
      "repo_provider": "github",
      "owner": "xlu2017",
      "repo": "agent-core",
      "branch": null,
      "path": "/opt/workstation/repos/agent-core",
      "repo_url": null
    }
  }
}
```

When `repo_url` is blank, the platform generates a GitHub HTTPS URL from `owner` and `repo`.

## API

```text
GET  /api/repo-sources
GET  /api/repo-sources/{service_name}
PUT  /api/repo-sources/{service_name}
POST /api/repo-sources/{service_name}/reset
```

`PUT` accepts:

```json
{
  "enabled": true,
  "repo_provider": "github",
  "owner": "acme",
  "repo": "agent-core-fork",
  "branch": "main",
  "path": "/opt/workstation/repos/agent-core-fork",
  "repo_url": null
}
```

## UI

The dashboard injects a **Repo sources** panel near the Services panel. It can edit owner, repo, branch, path, explicit repo URL, and enabled state for each repo-backed service.

## Compatibility environment variables

The registry still supports legacy environment variables as seed defaults:

```bash
AGENT_CORE_REPO_OWNER=...
AGENT_CORE_REPO_NAME=...
AGENT_CORE_REPO_URL=...
AGENT_CORE_REPO_PATH=...
AGENT_CORE_UPDATE_BRANCH=...

JUBILANT_GOGGLES_REPO_OWNER=...
JUBILANT_GOGGLES_REPO_NAME=...
JUBILANT_GOGGLES_REPO_URL=...
JUBILANT_GOGGLES_REPO_PATH=...
JUBILANT_GOGGLES_UPDATE_BRANCH=...
```

The environment values are seed/migration inputs. Once the JSON registry is edited, persisted registry data becomes the service mapping source.

## Safety boundary

Changing a repo source changes where Check Latest and Update Latest read from. It does not change credential provider selection and does not expose credentials to the browser.
