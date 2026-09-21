"""The committed swarm captures, exactly as the keyless API served them."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SWARM_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "surf" / "swarm"


def swarm_capture(name: str) -> Any:
    with open(SWARM_FIXTURES / f"{name}.json", encoding="utf-8") as fh:
        return json.load(fh)

# The 2026-09-21 corpus from api.imd.fun (plan A3); the old loader above retires in WP7.
SWARM_FIXTURES_V2 = SWARM_FIXTURES / "v2"


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
