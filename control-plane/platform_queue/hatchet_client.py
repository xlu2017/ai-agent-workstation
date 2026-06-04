"""Hatchet client initialization for the platform task queue."""

from __future__ import annotations

from hatchet_sdk import Hatchet


# Hatchet reads its connection settings from environment variables.
# Typical self-host/cloud values include HATCHET_CLIENT_TOKEN and related
# endpoint/TLS settings. Keep this module tiny so workers and submitters share
# exactly one client object.
hatchet = Hatchet()
