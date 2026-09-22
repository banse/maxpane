"""The committed swarm captures, exactly as the keyless API served them.

The 2026-09-21 corpus from api.imd.fun (swarm v2 plan A3) under
``fixtures/surf/swarm/v2``; the 2026-09-16 v1 captures that used to sit
beside it retired with their folds and widgets in WP7.

The 2026-09-21 ``/seats/{tokenId}`` captures (AGENT-seats plan WP0) sit under
``fixtures/surf/swarm/seats``, with their own ``MANIFEST.json``.
The owner-supplied 2026-09-22 BOARD captures sit under ``fixtures/surf/swarm/v3``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SWARM_FIXTURES_V2 = Path(__file__).resolve().parent / "fixtures" / "surf" / "swarm" / "v2"
SWARM_FIXTURES_SEATS = SWARM_FIXTURES_V2.parent / "seats"
SWARM_FIXTURES_V3 = SWARM_FIXTURES_V2.parent / "v3"


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


def swarm_capture_v3(name: str) -> dict:
    """One owner-supplied 2026-09-22 BOARD capture, or its provenance MANIFEST."""
    with open(SWARM_FIXTURES_V3 / f"{name}.json", encoding="utf-8") as fh:
        return json.load(fh)


def swarm_board_payload():
    """Frozen v3 contributor/worker facts and their independent source clocks."""
    from maxpane_dashboard.data import surf_swarm as fold
    contributors, workers = swarm_capture_v3('contributors'), swarm_capture_v3('workers')
    return dict(swarm_board_summary=fold.board_summary(contributors,workers),
                swarm_board_rows=fold.board_rows(contributors,workers),
                swarm_fleet=fold.fleet(workers),
                swarm_board_as_of_hhmm='03:01',swarm_workers_as_of_hhmm='04:02')


def swarm_agent_sources(token):
    """Independently folded v3 worker/contributor facts for exactly this seat."""
    from maxpane_dashboard.data import surf_swarm as fold
    return dict(swarm_seat_live=fold.seat_live(swarm_capture_v3("workers"), token),
                swarm_seat_contrib=fold.seat_contrib(swarm_capture_v3("contributors"), token),
                swarm_workers_as_of_hhmm="04:02", swarm_board_as_of_hhmm="03:01")


def swarm_capture_v5(name: str) -> dict:
    """One 2026-09-22 evening capture: ``work[]`` lists every attempt with its status."""
    with open(SWARM_FIXTURES_V3.parent / 'v5' / f'{name}.json', encoding='utf-8') as fh:
        return json.load(fh)


def swarm_capture_v4(name: str) -> dict:
    """One polish capture from 2026-09-22, including its provenance MANIFEST."""
    with open(SWARM_FIXTURES_V3.parent / 'v4' / f'{name}.json', encoding='utf-8') as fh:
        return json.load(fh)
