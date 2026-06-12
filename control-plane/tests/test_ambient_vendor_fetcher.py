import io
import json
import os
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch

CONTROL_PLANE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CONTROL_PLANE_ROOT))


def _make_zip_bytes(prefix: str = "owner-repo-abc123/", files: dict[str, bytes] | None = None) -> bytes:
    """Build a fake GitHub zipball in memory."""
    buf = io.BytesIO()
    file_map = files or {
        f"{prefix}README.md": b"# Hello\n",
        f"{prefix}src/main.py": b"print('hello')\n",
        f"{prefix}src/lib/__init__.py": b"",
    }
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in file_map.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_extract_zipball_strips_top_level_folder(tmp_path):
    from api.ambient_vendor.github_fetcher import extract_zipball

    target = tmp_path / "source"
    target.mkdir()
    zip_bytes = _make_zip_bytes()
    count = extract_zipball(zip_bytes, target)

    assert count == 3
    assert (target / "README.md").exists()
    assert (target / "src" / "main.py").exists()
    assert (target / "src" / "lib" / "__init__.py").exists()
    assert not (target / "owner-repo-abc123").exists()


def test_extract_zipball_empty_archive(tmp_path):
    from api.ambient_vendor.github_fetcher import extract_zipball

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w"):
        pass
    target = tmp_path / "source"
    target.mkdir()
    count = extract_zipball(buf.getvalue(), target)
    assert count == 0


def test_write_fetched_metadata_excludes_tokens(tmp_path):
    from api.ambient_vendor.github_fetcher import write_fetched_metadata

    target = tmp_path / "source"
    target.mkdir()
    metadata = {
        "owner": "microsoft",
        "repo": "playwright-python",
        "fetched_ref": "main",
        "fetched_at": "2025-01-01T00:00:00Z",
        "archive_url": "https://api.github.com/repos/microsoft/playwright-python/zipball/main",
        "archive_bytes": 1024,
        "secret_token": "ghp_SHOULD_NOT_APPEAR",
    }
    meta_path = write_fetched_metadata(target, metadata)

    stored = json.loads(meta_path.read_text())
    assert "secret_token" not in stored
    assert "ghp_SHOULD_NOT_APPEAR" not in meta_path.read_text()
    assert stored["owner"] == "microsoft"


def test_write_vendored_patches(tmp_path):
    from api.ambient_vendor.github_fetcher import write_vendored_patches

    target = tmp_path / "source"
    target.mkdir()
    patches_path = write_vendored_patches(target, "Playwright Python", "https://github.com/microsoft/playwright-python.git")

    assert patches_path.exists()
    content = patches_path.read_text()
    assert "Playwright Python" in content
    assert "microsoft/playwright-python" in content


def test_fetch_vendor_missing_auth(tmp_path):
    manifest = {
        "version": 1,
        "intent": "test",
        "selected_tools": [{
            "id": "test_tool",
            "name": "Test",
            "repo_url": "https://github.com/example/test.git",
            "github_owner": "example",
            "github_repo": "test",
            "target_dir": str(tmp_path / "source"),
            "role": "test",
            "collector_targets": [],
        }],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))

    with patch.dict(os.environ, {}, clear=True):
        with patch("api.ambient_vendor.service._get_token", return_value=None):
            from api.ambient_vendor.service import fetch_vendor
            result = fetch_vendor("test_tool", manifest_path=manifest_path)

    assert result.ok is False
    assert result.error is not None
    assert result.error["code"] == "GITHUB_AUTH_REQUIRED"


def test_fetch_vendor_with_mocked_archive(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True)
    (source_dir / ".gitkeep").touch()

    manifest = {
        "version": 1,
        "intent": "test",
        "selected_tools": [{
            "id": "test_tool",
            "name": "Test Tool",
            "repo_url": "https://github.com/example/test.git",
            "github_owner": "example",
            "github_repo": "test",
            "target_dir": str(source_dir),
            "role": "test",
            "collector_targets": [],
        }],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))

    zip_bytes = _make_zip_bytes()
    fake_metadata = {
        "owner": "example",
        "repo": "test",
        "fetched_ref": "main",
        "fetched_at": "2025-01-01T00:00:00Z",
        "archive_url": "https://api.github.com/repos/example/test/zipball/main",
        "archive_bytes": len(zip_bytes),
    }

    with patch("api.ambient_vendor.service._get_token", return_value="fake-token"):
        with patch(
            "api.ambient_vendor.service.fetch_zipball",
            return_value=(zip_bytes, fake_metadata),
        ):
            from api.ambient_vendor.service import fetch_vendor
            result = fetch_vendor("test_tool", manifest_path=manifest_path)

    assert result.ok is True
    assert result.source_present is True
    assert result.fetched_ref == "main"
    assert (source_dir / "README.md").exists()
    assert (source_dir / "src" / "main.py").exists()

    meta_path = source_dir.parent / "fetched_metadata.json"
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text())
    assert "fake-token" not in json.dumps(meta)


def test_fetch_vendor_refuses_nonempty_without_force(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True)
    (source_dir / "existing_file.py").write_text("# existing")

    manifest = {
        "version": 1,
        "intent": "test",
        "selected_tools": [{
            "id": "test_tool",
            "name": "Test",
            "repo_url": "https://github.com/example/test.git",
            "github_owner": "example",
            "github_repo": "test",
            "target_dir": str(source_dir),
            "role": "test",
            "collector_targets": [],
        }],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))

    with patch("api.ambient_vendor.service._get_token", return_value="fake-token"):
        from api.ambient_vendor.service import fetch_vendor
        result = fetch_vendor("test_tool", manifest_path=manifest_path)

    assert result.ok is False
    assert result.error["code"] == "TARGET_NOT_EMPTY"


def test_tokens_not_in_response_payloads(tmp_path):
    """Ensure token strings never appear in serialized results."""
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True)
    (source_dir / ".gitkeep").touch()

    manifest = {
        "version": 1,
        "intent": "test",
        "selected_tools": [{
            "id": "test_tool",
            "name": "Test",
            "repo_url": "https://github.com/example/test.git",
            "github_owner": "example",
            "github_repo": "test",
            "target_dir": str(source_dir),
            "role": "test",
            "collector_targets": [],
        }],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))

    zip_bytes = _make_zip_bytes()
    fake_meta = {
        "owner": "example",
        "repo": "test",
        "fetched_ref": "main",
        "fetched_at": "2025-01-01T00:00:00Z",
        "archive_url": "https://api.github.com/repos/example/test/zipball/main",
        "archive_bytes": len(zip_bytes),
    }

    with patch("api.ambient_vendor.service._get_token", return_value="ghp_supersecrettoken123"):
        with patch("api.ambient_vendor.service.fetch_zipball", return_value=(zip_bytes, fake_meta)):
            from api.ambient_vendor.service import fetch_vendor
            result = fetch_vendor("test_tool", manifest_path=manifest_path)

    serialized = json.dumps(result.model_dump())
    assert "ghp_supersecrettoken123" not in serialized


def test_api_endpoint_returns_vendor_status():
    """Smoke-test the FastAPI router with TestClient."""
    from fastapi.testclient import TestClient
    from api.routes.ambient_vendors import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    resp = client.get("/api/ambient/vendors")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "vendors" in body
    assert len(body["vendors"]) == 9


def test_api_endpoint_fetch_missing_auth():
    """Test that fetch endpoint returns GITHUB_AUTH_REQUIRED when no token."""
    from fastapi.testclient import TestClient
    from api.routes.ambient_vendors import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    with patch("api.ambient_vendor.service._get_token", return_value=None):
        resp = client.post("/api/ambient/vendors/playwright_python/fetch")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "GITHUB_AUTH_REQUIRED"
