import json
import sys
from pathlib import Path

CONTROL_PLANE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CONTROL_PLANE_ROOT))


def test_manifest_loads():
    from ambient.vendor_registry import load_manifest

    manifest = load_manifest()
    assert manifest["version"] == 1
    assert "selected_tools" in manifest
    assert len(manifest["selected_tools"]) > 0


def test_expected_vendor_ids_exist():
    from ambient.vendor_registry import load_manifest

    manifest = load_manifest()
    ids = {t["id"] for t in manifest["selected_tools"]}
    expected = {
        "playwright_python",
        "playwright",
        "tree_sitter",
        "watchfiles",
        "pygls",
        "pyte",
        "opentelemetry_python",
        "python_lsp_server",
        "source_map_js",
    }
    assert expected == ids


def test_registry_reports_source_present_false_for_empty_dirs():
    from ambient.vendor_registry import list_vendors

    vendors = list_vendors()
    for v in vendors:
        assert v["source_present"] is False, f"{v['id']} should report source_present=False"


def test_get_vendor_returns_none_for_unknown():
    from ambient.vendor_registry import get_vendor

    result = get_vendor("nonexistent_tool_xyz")
    assert result is None


def test_collector_target_map_complete():
    from ambient.vendor_registry import collector_target_map

    mapping = collector_target_map()
    assert "playwright_python" in mapping
    assert "browser_cdp" in mapping["playwright_python"]
    assert "tree_sitter" in mapping
    assert "source_mapping" in mapping["tree_sitter"]


def test_fetched_metadata_returns_none_when_absent():
    from ambient.vendor_registry import load_manifest, fetched_metadata

    manifest = load_manifest()
    for tool in manifest["selected_tools"]:
        assert fetched_metadata(tool) is None


def test_list_vendors_shape():
    from ambient.vendor_registry import list_vendors

    vendors = list_vendors()
    assert len(vendors) == 9
    for v in vendors:
        assert "id" in v
        assert "name" in v
        assert "repo_url" in v
        assert "collector_targets" in v
        assert isinstance(v["collector_targets"], list)
        assert "source_present" in v


def test_registry_with_custom_manifest(tmp_path):
    manifest = {
        "version": 1,
        "intent": "test",
        "selected_tools": [
            {
                "id": "test_tool",
                "name": "Test Tool",
                "repo_url": "https://github.com/example/test.git",
                "github_owner": "example",
                "github_repo": "test",
                "target_dir": str(tmp_path / "vendor" / "test_tool" / "source"),
                "role": "test",
                "collector_targets": ["test_target"],
            }
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    (tmp_path / "vendor" / "test_tool" / "source").mkdir(parents=True)

    from ambient.vendor_registry import list_vendors

    vendors = list_vendors(manifest_path)
    assert len(vendors) == 1
    assert vendors[0]["id"] == "test_tool"
    assert vendors[0]["source_present"] is False
