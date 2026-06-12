"""Knowledge routes (list, proposed triggers, approve)."""

import json

from fastapi import APIRouter, HTTPException

from api.config import KNOWLEDGE_DIR

router = APIRouter(tags=["knowledge"])


@router.get("/api/knowledge")
def list_knowledge():
    entries = []
    if KNOWLEDGE_DIR.exists():
        try:
            import yaml
            for f in sorted(KNOWLEDGE_DIR.glob("*.yaml")):
                try:
                    entry = yaml.safe_load(f.read_text())
                    if isinstance(entry, dict):
                        entries.append(entry)
                except Exception:
                    continue
        except ImportError:
            pass
    return {"entries": entries}


@router.get("/api/knowledge/proposed")
def list_proposed_triggers():
    proposed_dir = KNOWLEDGE_DIR / "proposed"
    if not proposed_dir.exists():
        return {"triggers": []}
    triggers = []
    for f in proposed_dir.glob("*"):
        try:
            import yaml
            triggers.append(yaml.safe_load(f.read_text()))
        except Exception:
            try:
                triggers.append(json.loads(f.read_text()))
            except Exception:
                continue
    return {"triggers": triggers}


@router.post("/api/knowledge/approve/{trigger_id}")
def approve_knowledge_trigger(trigger_id: str):
    from postmortem import approve_trigger
    if approve_trigger(trigger_id):
        return {"status": "approved", "trigger_id": trigger_id}
    raise HTTPException(404, f"Trigger '{trigger_id}' not found")
