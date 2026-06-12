from pathlib import Path


def test_frontend_server_apps_panel_is_wired():
    web_src = Path(__file__).parents[1] / "web" / "src"
    main_content = (web_src / "main.tsx").read_text()
    panel_content = (web_src / "server-app-panel.ts").read_text()
    catalog_content = (web_src / "server-app-catalog.ts").read_text()
    css_content = (web_src / "server-app-launcher.css").read_text()

    assert "./server-app-panel" in main_content
    assert "./server-app-launcher.css" in main_content
    assert "server-app-launcher-enhancer" in panel_content
    assert "POPULAR_SERVER_APPS" in catalog_content
    assert "searchServerApps" in catalog_content
    assert ".as-app-launcher-panel" in css_content
