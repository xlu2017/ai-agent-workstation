"""API routes for ambient-context vendor management."""

from __future__ import annotations

from fastapi import APIRouter

from api.ambient_vendor.models import VendorFetchRequest
from api.ambient_vendor.registry import get_vendor_entry, list_vendor_entries
from api.ambient_vendor.service import fetch_all_vendors, fetch_vendor

router = APIRouter(prefix="/api/ambient/vendors", tags=["ambient-vendors"])


@router.get("")
def list_vendors():
    entries = list_vendor_entries()
    return {"ok": True, "vendors": [e.model_dump() for e in entries]}


@router.get("/{tool_id}")
def get_vendor(tool_id: str):
    entry = get_vendor_entry(tool_id)
    if not entry:
        return {"ok": False, "error": {"code": "UNKNOWN_TOOL", "message": f"Tool '{tool_id}' not found."}}
    return {"ok": True, "vendor": entry.model_dump()}


@router.post("/{tool_id}/fetch")
def fetch_single_vendor(tool_id: str, body: VendorFetchRequest | None = None):
    req = body or VendorFetchRequest()
    result = fetch_vendor(tool_id, ref=req.ref, force=req.force)
    return result.model_dump()


@router.post("/fetch-all")
def fetch_all():
    results = fetch_all_vendors()
    return {
        "ok": all(r.ok for r in results),
        "results": [r.model_dump() for r in results],
    }
