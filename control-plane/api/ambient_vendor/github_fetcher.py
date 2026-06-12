"""Server-side GitHub archive fetcher for ambient-context vendors.

Downloads upstream source via the GitHub REST API zipball endpoint
using a server-side token.  Never exposes the token in logs, metadata,
or response payloads.
"""

from __future__ import annotations

import io
import json
import logging
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


def _sanitize(msg: str) -> str:
    """Strip tokens from any log/error string."""
    for env_key in ("GITHUB_TOKEN", "GITHUB_PAT", "PAT"):
        token = os.environ.get(env_key)
        if token and token in msg:
            msg = msg.replace(token, "***")
    return msg


def fetch_zipball(
    owner: str,
    repo: str,
    token: str,
    ref: str | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """Download a GitHub zipball archive.

    Returns (zip_bytes, metadata_dict).
    """
    ref_part = ref or ""
    url = f"{GITHUB_API}/repos/{owner}/{repo}/zipball/{ref_part}".rstrip("/")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "ambient-vendor-fetcher",
    }

    logger.info("Fetching archive for %s/%s ref=%s", owner, repo, ref or "default")

    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=120) as resp:
            data = resp.read()
    except HTTPError as exc:
        sanitized = _sanitize(str(exc))
        raise RuntimeError(f"GitHub archive download failed: {sanitized}") from exc

    metadata = {
        "owner": owner,
        "repo": repo,
        "fetched_ref": ref or "default_branch",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "archive_url": f"{GITHUB_API}/repos/{owner}/{repo}/zipball/{ref_part}".rstrip("/"),
        "archive_bytes": len(data),
    }

    return data, metadata


def extract_zipball(zip_bytes: bytes, target_dir: Path) -> int:
    """Extract a GitHub zipball into *target_dir*, stripping the top-level folder.

    Returns the number of extracted entries.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO(zip_bytes)
    count = 0

    with zipfile.ZipFile(buf) as zf:
        entries = zf.namelist()
        if not entries:
            return 0

        prefix = entries[0]
        if not prefix.endswith("/"):
            prefix = prefix.split("/")[0] + "/"

        for entry in entries:
            if not entry.startswith(prefix):
                continue
            relative = entry[len(prefix):]
            if not relative:
                continue

            dest = target_dir / relative
            if entry.endswith("/"):
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(entry))
                count += 1

    return count


def write_fetched_metadata(target_dir: Path, metadata: dict[str, Any]) -> Path:
    """Persist fetch metadata alongside the source directory.

    The metadata file lives at ``<tool_dir>/fetched_metadata.json`` (one level
    above source/).  Tokens are never written.
    """
    safe = {k: v for k, v in metadata.items() if "token" not in k.lower()}
    meta_path = target_dir.parent / "fetched_metadata.json"
    meta_path.write_text(json.dumps(safe, indent=2) + "\n")
    return meta_path


def write_vendored_patches(target_dir: Path, tool_name: str, repo_url: str) -> Path:
    patches = target_dir / "VENDORED_PATCHES.md"
    if not patches.exists():
        patches.write_text(
            f"# Vendored patches: {tool_name}\n\n"
            "Document all local changes to this vendored source tree here.\n\n"
            f"Upstream: {repo_url}\n"
        )
    return patches
