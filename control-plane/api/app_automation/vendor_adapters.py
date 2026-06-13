from __future__ import annotations

from api.app_automation.adapter_base import VendorAdapter


class ActivepiecesAdapter(VendorAdapter):
    vendor_id = "activepieces"


class ComposioAdapter(VendorAdapter):
    vendor_id = "composio"


class McpServersAdapter(VendorAdapter):
    vendor_id = "mcp_servers"


class N8nAdapter(VendorAdapter):
    vendor_id = "n8n"


class StagehandAdapter(VendorAdapter):
    vendor_id = "stagehand"


class BrowserUseAdapter(VendorAdapter):
    vendor_id = "browser_use"


class SkyvernAdapter(VendorAdapter):
    vendor_id = "skyvern"
