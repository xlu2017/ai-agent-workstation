#!/usr/bin/env python3
"""Fetch ambient-context vendor source trees using server-side GitHub auth.

This script calls the same service logic used by the FastAPI ambient vendor
endpoints.  It does not use SSH or require local developer credentials.

Usage:
  python3 control-plane/scripts/vendor_ambient_context_tools.py --tool playwright_python
  python3 control-plane/scripts/vendor_ambient_context_tools.py --all
  python3 control-plane/scripts/vendor_ambient_context_tools.py --tool pygls --ref main
  python3 control-plane/scripts/vendor_ambient_context_tools.py --tool pygls --force
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CONTROL_PLANE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CONTROL_PLANE_ROOT))

from api.ambient_vendor.service import fetch_all_vendors, fetch_vendor  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch ambient-context vendor source using server-side GitHub auth.",
    )
    parser.add_argument("--tool", action="append", help="Vendor tool id to fetch. Can be repeated.")
    parser.add_argument("--all", action="store_true", help="Fetch all vendors in the manifest.")
    parser.add_argument("--ref", default=None, help="Git ref (branch/tag/commit) to fetch.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing source content.")
    args = parser.parse_args()

    if not args.all and not args.tool:
        parser.error("Specify --tool <id> or --all")

    if args.all:
        results = fetch_all_vendors(ref=args.ref, force=args.force)
    else:
        results = []
        for tool_id in args.tool:
            results.append(fetch_vendor(tool_id, ref=args.ref, force=args.force))

    any_failed = False
    for r in results:
        payload = r.model_dump()
        print(json.dumps(payload, indent=2))
        if not r.ok:
            any_failed = True

    if any_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
