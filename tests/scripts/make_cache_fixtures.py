"""Write the pre-branch cache fixtures under ``tests/fixtures/cache/``.

Provenance for the Branch 9 (`refactor/series-cache`) acceptance tests.
``SeriesCache`` took over the persistence of six cache classes; the claim
that the persisted *shape* did not change is only worth something if the
files the tests load were written by the code that existed **before** the
refactor.  So the fixtures are generated from a git worktree of the
pre-branch commit, never from the branch's own classes::

    git worktree add <wt> 53a71d5
    PYTHONPATH=<wt> .venv/bin/python tests/scripts/make_cache_fixtures.py <wt>
    git worktree remove <wt>

``PYTHONPATH`` has to win over the editable install, which otherwise
resolves ``maxpane_dashboard`` back into the working checkout -- i.e. into
exactly the code under test.  The script therefore refuses to run unless
``maxpane_dashboard.__file__`` is inside the worktree it was given.

**This script is never executed by a test.**  It lives in the repo as the
record of how those JSON files came to exist, so the next person can
regenerate them from any commit rather than trusting a blob.  Re-running
it overwrites the fixtures; the point of committing them is that nobody
needs to.

Determinism: every timestamp is a literal derived from ``BASE_TS``
(1_758_000_000.0), and ``saved_at`` -- the one field the cache classes
stamp from the wall clock -- is rewritten to ``BASE_TS`` afterwards, so
two runs a week apart produce byte-identical files.  The samples run
*up to* ``BASE_TS`` rather than past it, so a test loading them with
``now=BASE_TS`` is not leaning on ``CLOCK_SKEW_TOLERANCE_SECONDS`` to
keep the last point alive.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BASE_TS = 1_758_000_000.0
STEP = 30.0  # the dashboards' poll interval
POINTS = 6

OUT_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "cache"


def _require_worktree(worktree: str) -> None:
    """Refuse to run against the working checkout's own code."""
    import maxpane_dashboard

    resolved = os.path.realpath(maxpane_dashboard.__file__)
    expected = os.path.realpath(worktree)
    if not resolved.startswith(expected + os.sep):
        raise SystemExit(
            f"maxpane_dashboard resolves to {resolved}, which is not inside "
            f"{expected}. Prepend the worktree to PYTHONPATH: the editable "
            f"install otherwise wins and the fixture would be written by the "
            f"very code it is meant to pin."
        )
    print(f"maxpane_dashboard -> {resolved}")


def _freeze_saved_at(path: Path) -> None:
    payload = json.loads(path.read_text())
    payload["saved_at"] = BASE_TS
    path.write_text(json.dumps(payload))


def make_cattown() -> Path:
    from maxpane_dashboard.data.cattown_cache import CatTownCache
    from maxpane_dashboard.data.cattown_models import (
        CatTownSnapshot,
        CompetitionEntry,
        CompetitionState,
        KibbleEconomy,
        StakingState,
    )

    kibble = KibbleEconomy(
        price_eth=1.0e-7,
        total_supply=1_000_000.0,
        circulating=900_000.0,
        burned=100_000.0,
        staked_total=50_000.0,
        price_change_24h=0.0,
    )
    staking = StakingState(
        total_staked=50_000.0,
        user_staked=0.0,
        pending_rewards=0.0,
        weekly_revenue=0.0,
    )

    cache = CatTownCache(max_history=120)
    for i in range(POINTS):
        ts = BASE_TS - (POINTS - 1 - i) * STEP
        entry = CompetitionEntry(
            fisher_address="0x" + "11" * 20,
            # A different value per point, so a fixture round-trip that
            # silently loaded the wrong series could not pass.
            fish_weight_kg=3.5 + i * 0.25,
            fish_species="Tuna",
            rarity="rare",
            rank=1,
        )
        competition = CompetitionState(
            week_number=7,
            is_active=True,
            total_volume_kibble=10_000.0 + i * 100.0,
            prize_pool_kibble=1_000.0 + i * 10.0,
            treasure_pool_kibble=7_000.0,
            staker_revenue_kibble=1_000.0,
            num_participants=12,
            start_time=int(BASE_TS) - 3600,
            end_time=int(BASE_TS) + 3600,
            entries=[entry],
        )
        snapshot = CatTownSnapshot(
            fetched_at=ts,
            kibble=kibble,
            competition=competition,
            recent_catches=[],
            staking=staking,
        )
        cache.update(
            snapshot,
            leader_weight_kg=entry.fish_weight_kg,
            raffle_total_tickets=100 + i * 5,
        )

    path = OUT_DIR / "cattown_53a71d5.json"
    cache.save_to_file(str(path))
    _freeze_saved_at(path)
    return path


def make_dota() -> Path:
    from maxpane_dashboard.data.dota_cache import DOTACache
    from maxpane_dashboard.data.dota_models import (
        DOTABase,
        DOTAGameState,
        DOTALane,
        DOTASnapshot,
    )

    cache = DOTACache(max_history=120)
    base = DOTABase(hp=1_000, maxHp=1_000)
    for i in range(POINTS):
        ts = BASE_TS - (POINTS - 1 - i) * STEP
        state = DOTAGameState(
            tick=i,
            agents={},
            lanes={
                "top": DOTALane(human=5, orc=5, frontline=10 + i),
                "mid": DOTALane(human=5, orc=5, frontline=20 + 2 * i),
                "bot": DOTALane(human=5, orc=5, frontline=30 + 3 * i),
            },
            towers=[],
            bases={"human": base, "orc": base},
            heroes=[],
            winner=None,
        )
        cache.update(DOTASnapshot(fetched_at=ts, game_state=state))

    path = OUT_DIR / "dota_53a71d5.json"
    cache.save_to_file(str(path))
    _freeze_saved_at(path)
    return path


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {sys.argv[0]} <path-to-53a71d5-worktree>")
    _require_worktree(sys.argv[1])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in (make_cattown(), make_dota()):
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
