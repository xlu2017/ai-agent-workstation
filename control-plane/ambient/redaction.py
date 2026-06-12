from __future__ import annotations

import copy
import re
from typing import Any

from ambient.types import PrivacyMark

SECRET_FIELD_NAMES = {
    "authorization",
    "cookie",
    "set-cookie",
    "password",
    "passwd",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "private_key",
    "client_secret",
}

SECRET_PATTERNS = [
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]{20,}", re.IGNORECASE),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"tskey-[A-Za-z0-9\-]+"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
    re.compile(r"(?i)(password|secret|token|api[_-]?key)\s*[:=]\s*[^\s,;]+"),
]


def _is_secret_field(name: str) -> bool:
    lowered = name.lower().replace("-", "_")
    return lowered in SECRET_FIELD_NAMES or any(part in lowered for part in ("password", "secret", "token"))


def redact_text(value: str) -> tuple[str, bool]:
    redacted = value
    changed = False
    for pattern in SECRET_PATTERNS:
        next_value = pattern.sub("[redacted]", redacted)
        if next_value != redacted:
            changed = True
            redacted = next_value
    return redacted, changed


def redact_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], PrivacyMark]:
    """Return a redacted deep copy plus a privacy mark.

    Redaction runs before persistence. This is intentionally deterministic and
    conservative; later collectors can add source-specific redactors.
    """

    redacted_fields: list[str] = []

    def visit(value: Any, path: str) -> Any:
        nonlocal redacted_fields
        if isinstance(value, dict):
            next_dict = {}
            for key, item in value.items():
                key_text = str(key)
                child_path = f"{path}.{key_text}" if path else key_text
                if _is_secret_field(key_text):
                    redacted_fields.append(child_path)
                    next_dict[key] = "[redacted]"
                else:
                    next_dict[key] = visit(item, child_path)
            return next_dict
        if isinstance(value, list):
            return [visit(item, f"{path}[{idx}]") for idx, item in enumerate(value)]
        if isinstance(value, str):
            redacted, changed = redact_text(value)
            if changed:
                redacted_fields.append(path or "<text>")
            return redacted
        return value

    copied = copy.deepcopy(payload)
    redacted_payload = visit(copied, "")
    mark = PrivacyMark(
        contains_secret=bool(redacted_fields),
        redaction_applied=bool(redacted_fields),
        redacted_fields=sorted(set(redacted_fields)),
    )
    return redacted_payload, mark
