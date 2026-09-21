"""The committed swarm captures, exactly as the keyless API served them.

The 2026-09-21 corpus from api.imd.fun (swarm v2 plan A3) under
``fixtures/surf/swarm/v2``; the 2026-09-16 v1 captures that used to sit
beside it retired with their folds and widgets in WP7.

The 2026-09-21 ``/seats/{tokenId}`` captures (AGENT-seats plan WP0) sit under
``fixtures/surf/swarm/seats``, with their own ``MANIFEST.json``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SWARM_FIXTURES_V2 = Path(__file__).resolve().parent / "fixtures" / "surf" / "swarm" / "v2"
SWARM_FIXTURES_SEATS = SWARM_FIXTURES_V2.parent / "seats"


def swarm_capture_v2(name: str) -> Any:
    with open(SWARM_FIXTURES_V2 / f"{name}.json", encoding="utf-8") as fh:
        return json.load(fh)


def swarm_details_v2() -> dict[str, Any]:
    """Every ``v2/details/<job-id>.json`` keyed by job id (the file stem), sorted."""
    out: dict[str, Any] = {}
    for path in sorted((SWARM_FIXTURES_V2 / "details").glob("*.json")):
        with open(path, encoding="utf-8") as fh:
            out[path.stem] = json.load(fh)
    return out


def swarm_manifest_v2() -> dict[str, Any]:
    return swarm_capture_v2("MANIFEST")


def swarm_seat_capture(name: str) -> dict:
    """One ``fixtures/surf/swarm/seats/<name>.json``, e.g. ``seat_420`` or ``MANIFEST``."""
    with open(SWARM_FIXTURES_SEATS / f"{name}.json", encoding="utf-8") as fh:
        return json.load(fh)
