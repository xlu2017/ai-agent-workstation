"""
Central redaction helper for execution outputs.

Used before returning or persisting:
  - tool arg summaries
  - command previews
  - command stdout/stderr summaries
  - event metadata
  - result output
  - error messages
  - outcome records to agent-core
"""

from __future__ import annotations

import re
from typing import Any

# Patterns that indicate secret-looking values
_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ghp_[A-Za-z0-9]{36,}"),           # GitHub PAT (classic)
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),    # GitHub PAT (fine-grained)
    re.compile(r"tskey-[A-Za-z0-9\-]{20,}"),         # Tailscale auth key
    re.compile(r"sk-[A-Za-z0-9]{20,}"),              # OpenAI / generic API key
    re.compile(r"Bearer\s+[A-Za-z0-9\-_.~+/]{20,}", re.IGNORECASE),  # Bearer tokens
    re.compile(r"Authorization:\s*\S+", re.IGNORECASE),               # Auth headers
    re.compile(r"password\s*=\s*\S+", re.IGNORECASE),                 # password= values
    re.compile(r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----.*?-----END", re.DOTALL),  # SSH keys
]

# Env var names whose values must be scrubbed if they appear literally
_SECRET_ENV_NAMES = {
    "RDP_PASSWORD",
    "TAILSCALE_AUTH_KEY",
    "PAT",
    "GITHUB_TOKEN",
    "GITHUB_PAT",
    "LITELLM_MASTER_KEY",
    "OPENAI_API_KEY",
}


def redact_string(text: str) -> str:
    """Redact secret-looking patterns from a string."""
    if not text:
        return text
    result = text
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    return result


def redact_value(value: Any) -> Any:
    """Recursively redact secret-looking values from any structure."""
    if isinstance(value, str):
        return redact_string(value)
    if isinstance(value, dict):
        return {k: redact_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(redact_value(item) for item in value)
    return value


def redact_env_values(text: str) -> str:
    """Scrub known environment variable values from output text.

    Reads actual env var values and replaces them in the text.
    Only scrubs variables listed in _SECRET_ENV_NAMES.
    """
    import os

    result = text
    for name in _SECRET_ENV_NAMES:
        val = os.environ.get(name, "")
        if val and len(val) > 3 and val in result:
            result = result.replace(val, f"[REDACTED:{name}]")
    return result


def redact_output(text: str) -> str:
    """Full redaction pass: patterns + env values."""
    return redact_env_values(redact_string(text))


def is_secret_ref(value: str) -> bool:
    """Check if a value is a safe secret reference (not a raw secret).

    Allowed: secret_name, secret_ref, $PAT (label), ${VAR_NAME}
    """
    if not isinstance(value, str):
        return False
    # $VAR or ${VAR} is a reference, not a raw value
    if value.startswith("$"):
        return True
    return False
