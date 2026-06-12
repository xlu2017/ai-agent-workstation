"""Model listing route."""

import json
import urllib.request
from pathlib import Path

from fastapi import APIRouter

from api.config import LITELLM_URL

router = APIRouter(tags=["models"])


@router.get("/api/models")
def list_models():
    models = []

    try:
        req = urllib.request.urlopen(f"{LITELLM_URL}/models", timeout=5)
        data = json.loads(req.read())
        models = data.get("data", [])
    except Exception:
        pass

    config_path = Path("/opt/workstation/config/litellm_config.yaml")
    config_models = []
    if config_path.exists():
        try:
            import yaml
            config = yaml.safe_load(config_path.read_text())
            config_models = config.get("model_list", [])
        except Exception:
            pass

    return {"live": models, "configured": config_models}
