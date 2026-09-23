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


def swarm_oracle_capture(name: str) -> dict:
    """One unmodified 2026-09-23 oracle capture, including seat_420 and MANIFEST."""
    with open(SWARM_FIXTURES_V3.parent / 'oracle' / f'{name}.json', encoding='utf-8') as fh:
        return json.load(fh)


#: The oracle request details committed from the 2026-09-23 capture (245 bodies):
#: the first 40 RECORD rows of ``oracle/seat_420`` and of v4 ``seat_420``, plus
#: the first capture of each panel case. The rest were dropped on 2026-09-24
#: (19 MB); ``MANIFEST.json`` keeps every sha256 and marks them ``committed:
#: false``. Hand-listed so a missing file fails loudly rather than shrinking a scan.
SWARM_ORACLE_DETAIL_IDS: tuple[str, ...] = (
    "005a4ed9-8e78-41fa-a7b4-b86fec5c8f09",
    "02505ccf-5ff6-47ca-8a90-7b8bad94e51a",
    "04c534b8-8a2c-431b-9375-d517725e41a4",
    "05e0546f-927a-4655-9ac0-7ce8236feb0c",
    "0674f6d0-dd54-4b30-8e42-29e83754c8f0",
    "07747e14-6ff9-43d4-9278-20811f505560",
    "07f327e5-b83d-4e9b-a969-c1910345e6f4",
    "085924f4-8797-4369-8d7e-32d65d7ab072",
    "08f59ace-2c7c-4e3b-b1b2-b0788666ea27",
    "0a926771-1d74-42d3-8b37-4214b8e41da1",
    "0abb05ab-078d-4815-8039-a8ab1b5a02fc",
    "0b38a215-127f-4ae0-8f6f-cff515577603",
    "0d549b1c-31f2-4a17-9737-3660e575b4cc",
    "10b728ec-679a-46dc-8beb-cdc900355bbd",
    "11a12ed2-3f62-431d-9a19-f5bb5783ce51",
    "141d4e30-3bc4-41c1-99a3-9cb489883cc8",
    "1898659f-f180-4237-91af-1b0c03673a21",
    "1fb7dfef-c85f-4505-8776-f0dc433a0974",
    "2398659b-27d3-4163-9d8b-2fb59c5ecc30",
    "254b54c7-2309-4da3-b24f-2397162b24f7",
    "280cb8c1-f8f1-452c-9ff2-7e4cabec3ad6",
    "2bd47834-c7ff-4a98-b581-1ac21c71587f",
    "2c2e1815-1a9b-4f48-ae81-822486193185",
    "35335001-74dc-49dc-820c-5ef111338287",
    "3558c5dc-c2ca-4d0b-aff1-a0fd8bb34906",
    "3735bbf0-6bd2-453a-90a5-b0d2c65a942b",
    "37af018f-cac7-4001-9078-1e9a370bbb29",
    "3b1fd330-0185-4b39-bcd5-e399177efbe2",
    "426f378a-4f6e-4907-8dc2-b13bbfdf767d",
    "44f4bf62-ad87-4f42-8900-51d8531b89d7",
    "48030cbe-24b6-4c97-9818-c259b8b6657a",
    "50f47ec0-80c6-492b-8461-517afb9f7acf",
    "540c570c-8c66-4681-a921-31bfafa9a279",
    "59765c35-cbd3-41c2-a916-638ba22f252a",
    "5a3ed1e2-7f54-46e1-9c6e-af25828ccc81",
    "5b2c8acb-9351-41c1-b18b-db472cee8da1",
    "6149c315-1989-4bc8-ae0e-e9493233ae84",
    "6a6c3e31-0643-4602-b32e-edb5f4514590",
    "6d2b61d2-1c5a-485a-9909-818952bd9985",
    "7256df1b-8c01-4903-b6e5-abb7a7bbde7c",
    "76ed2012-053e-4a76-8f31-e01510723963",
    "796637c0-3422-4997-b5cf-a29678cecadb",
    "7a2458fc-abcb-48e0-ba59-72f12e2f3bc8",
    "7a552f7f-bfd3-4a5a-9485-188e166bc1d5",
    "7b383d87-b211-4f8f-bdd4-37bf369b477a",
    "7d86b32c-c65d-4f85-a599-c99db1bb071d",
    "85467b52-2c57-48ce-aa62-b83605e911a8",
    "868cf0af-35bb-4654-b3e9-45179b83e4a2",
    "8886cca0-1b25-42cb-b9e0-1454891d9f6a",
    "8f353284-92c5-4b0e-9c1b-9f991fe9c79e",
    "939edd81-6a1e-4b0a-8925-5313c6b6f1cb",
    "944177b4-65af-40cf-8d01-f713a4e1c705",
    "9857a440-4204-452b-95e5-58347d2716c9",
    "98c57c0d-f328-4a55-88c7-60b35cfd360e",
    "9b80f9b5-594f-4f79-852d-11788875f503",
    "9c68a5f8-eeee-4eeb-bc2a-19b4330133fe",
    "a2750009-7da2-40c2-a9e2-2f0889592315",
    "a2e5d7fc-462c-4c93-9a64-9fcc4f8c2dd9",
    "a3ad758f-5f6b-4b97-afd3-c874760a93b8",
    "a79173eb-81bd-4336-b4e1-e84ee34c0370",
    "adbbfbb5-c6d3-4e47-adad-df7536d0ba3e",
    "ae17564e-5305-496a-ba7b-d5d3ed2d4232",
    "afe9509c-c8b7-4b7c-9c61-4b499e0562c7",
    "b37256c4-3afb-4be1-b2d1-f1cdef077256",
    "b4a872c9-0de5-40ae-9958-8a4c4aa72ea0",
    "b62b3491-0c6a-4cbf-b806-da7c589a14e9",
    "b7957c46-a869-4a61-bfb8-9d5860fa8470",
    "c0305cf0-7a04-473c-89e1-b7181093cc3e",
    "c069469a-d8d2-4bf2-a415-e01d2263d168",
    "cb54d60b-78d9-4443-8193-e6cb01d99c59",
    "d69d1afa-7368-46ce-b4d0-3148e5d6293f",
    "d88995bf-e9f3-4c94-a0eb-0ab57274616f",
    "db8fdb24-c365-4e7c-af30-c7a64bc8c03d",
    "e18ee544-0cfc-47c6-a3ba-ba51b11cbf1f",
    "e3edfd5f-6f52-4a54-bc9d-45780aa5a5c4",
    "e57e86e9-19c7-4f22-be42-d1e04ee1c93d",
    "e84a70fe-651a-4886-a5e5-3befff1ddb14",
    "eca2be09-caf4-4311-8751-8da6efd45bcd",
    "ecf525e8-ecf0-4f7c-9010-99beed941f74",
    "f01018ad-bffb-49ff-883c-82440e7c39d4",
    "f4d77ccb-9f0d-45ad-9d28-f6c969a1f214",
    "f71242da-9393-4dbc-b08f-328a193eeeed",
    "fa91fe5b-2d50-4059-a44c-f1418ac54d2d",
)


def swarm_oracle_details() -> list[dict]:
    """Every committed detail, in :data:`SWARM_ORACLE_DETAIL_IDS` order."""
    return [swarm_oracle_capture(f'request_{request_id}') for request_id in SWARM_ORACLE_DETAIL_IDS]


def swarm_oracle_rows(rows: list[dict]) -> list[dict]:
    """Join captured detail evidence onto existing rows through the production fold."""
    from maxpane_dashboard.data import surf_swarm as fold
    oracle = {}
    for detail in swarm_oracle_details():
        for row in rows:
            if row['job_id'] == detail['jobId']:
                point = fold.oracle_point(detail, row['job_id'], row['submission_hash'], now_ts=1000.)
                if point is not None:
                    oracle.setdefault(row['job_id'], {})[row['submission_hash']] = point
    return fold.enrich_panel_rows(rows, oracle, fold.SWARM_ORACLE_NODE_KEYS)
