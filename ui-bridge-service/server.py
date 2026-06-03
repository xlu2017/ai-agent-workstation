"""
UI-to-Code Bridge Service — Source Map Resolution Server

Phase 1: Scaffolding with stub resolution logic.
Future: Full source map parsing and component-to-file resolution.

Endpoints:
    POST /api/resolve  — Resolve UI element to source code location
    GET  /api/health   — Health check
    GET  /api/status   — Service status and supported frameworks

Runs on port 9876 by default.
"""

import json
import os
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ.get("BRIDGE_PORT", "9876"))


@dataclass
class SourceLocation:
    file: str | None = None
    line: int | None = None
    column: int | None = None
    component: str | None = None
    framework: str | None = None
    confidence: float = 0.0


def resolve_element(metadata: dict) -> SourceLocation:
    """
    Resolve UI element metadata to source code location.

    Phase 1: Uses React _debugSource if available.
    Future phases will:
      - Parse source maps from dev server
      - Query Vite/Next.js source map APIs
      - Use Chrome DevTools Protocol for coverage data
      - Cross-reference component tree with file system
    """
    location = SourceLocation()

    # Check React debug source (available in development builds)
    react_info = metadata.get("react")
    if react_info:
        location.framework = "react"
        if react_info.get("type"):
            location.component = react_info["type"]
        source = react_info.get("source")
        if source:
            location.file = source.get("fileName")
            location.line = source.get("lineNumber")
            location.column = source.get("columnNumber")
            location.confidence = 0.95
        elif react_info.get("type"):
            # Component name known but no source — can grep for it
            location.confidence = 0.3

    return location


class BridgeHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/api/resolve":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            metadata = json.loads(body)

            location = resolve_element(metadata)
            response = {
                "file": location.file,
                "line": location.line,
                "column": location.column,
                "component": location.component,
                "framework": location.framework,
                "confidence": location.confidence,
                "metadata": metadata,
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path == "/api/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        elif self.path == "/api/status":
            status = {
                "service": "ui-bridge",
                "version": "0.1.0",
                "phase": 1,
                "supported_frameworks": ["react", "next.js", "vite", "vue (planned)"],
                "resolution_methods": [
                    "react_debug_source",
                    "source_map_parsing (planned)",
                    "vite_api (planned)",
                    "cdp_coverage (planned)",
                ],
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(status).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        print(f"[bridge] {args[0]}")


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), BridgeHandler)
    print(f"[bridge] UI-to-Code Bridge Service running on port {PORT}")
    print(f"[bridge] Phase 1: React _debugSource resolution")
    server.serve_forever()
