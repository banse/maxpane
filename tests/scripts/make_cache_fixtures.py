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


def _bakery_models():
    """Import the bakery models from whichever tree is on ``PYTHONPATH``."""
    from maxpane_dashboard.data.models import (
        AgentConfig,
        BakerySummary,
        Contracts,
        GameplayCaps,
        LiveState,
        Network,
        ReferralWeights,
        Season,
    )
    from maxpane_dashboard.data.snapshot import GameSnapshot

    return (
        AgentConfig,
        BakerySummary,
        Contracts,
        GameplayCaps,
        LiveState,
        Network,
        ReferralWeights,
        Season,
        GameSnapshot,
    )


def make_bakery() -> Path:
    """Three bakeries x six cookie-count points, no season reset.

    Counts climb monotonically: a collapse below
    ``SEASON_RESET_DROP_RATIO`` of the previous sample would clear the
    bakery's deque mid-fixture, and a fixture whose own generator trips
    the reset logic proves nothing about a reload.
    """
    from maxpane_dashboard.data.cache import DataCache

    (
        AgentConfig,
        BakerySummary,
        Contracts,
        GameplayCaps,
        LiveState,
        Network,
        ReferralWeights,
        Season,
        GameSnapshot,
    ) = _bakery_models()

    season = Season(
        id=3,
        start_time=str(int(BASE_TS) - 86_400),
        end_time=str(int(BASE_TS) + 86_400),
        claim_deadline=None,
        protocol_fee_bps=0,
        seed_amount="1000000",
        results_root=None,
        finalized=False,
        ended=False,
        is_active=True,
        prize_pool="2000000",
    )
    agent_config = AgentConfig(
        name="Bakery",
        version="1.0",
        generated_at="2026-03-27T04:26:31.659Z",
        network=Network(
            name="Abstract",
            chain_id=2741,
            rpc_http="https://api.mainnet.abs.xyz",
            explorer="https://abscan.org",
            currency="ETH",
            wallet_model="Abstract Global Wallet",
        ),
        contracts=Contracts(
            season_manager="0x1",
            prize_pool="0x2",
            player_registry="0x3",
            clan_registry="0x4",
            boost_manager="0x5",
            bakery="0x6",
        ),
        live_state=LiveState(
            current_season_id=3,
            is_season_active=True,
            buy_in_wei="2000000000000000",
            buy_in_eth="0.002",
            vrf_fee_wei="22006155000000",
            vrf_fee_eth="0.000022006155",
            minimum_required_wei_excluding_gas="2022006155000000",
            minimum_required_eth_excluding_gas="0.002022006155",
            referral_weights=ReferralWeights(
                referred_weight_bps=10500,
                not_referred_weight_bps=10000,
                referral_bonus_bps=500,
            ),
            gameplay_caps=GameplayCaps(
                cookie_scale=10_000,
                max_active_boosts=5,
                max_active_debuffs=5,
                leave_penalty_bps=10_000,
            ),
            active_boost_catalog=(),
        ),
        live_data_status="fresh",
    )

    def bakery(index: int, name: str, tx_count: int) -> object:
        return BakerySummary(
            id=index,
            name=name,
            creator="0x" + f"{index:02d}" * 20,
            leader="0x" + f"{index:02d}" * 20,
            top_cook=None,
            member_count=10 + index,
            active_cook_count=2,
            season_id=3,
            created_at=str(int(BASE_TS) - 7200),
            tx_count=str(tx_count),
            raw_tx_count=str(tx_count),
            buffs=0,
            debuffs=0,
            active_buffs=(),
            active_debuffs=(),
        )

    cache = DataCache(max_history=120)
    for i in range(POINTS):
        ts = BASE_TS - (POINTS - 1 - i) * STEP
        # A different slope per bakery, so a round-trip that loaded the
        # wrong key could not pass.
        snapshot = GameSnapshot(
            season=season,
            bakeries=[
                bakery(1, "Sourdough Syndicate", 1_000_000 + i * 10_000),
                bakery(2, "Rye Republic", 500_000 + i * 20_000),
                bakery(3, "Crumb Cartel", 250_000 + i * 30_000),
            ],
            activity=[],
            agent_config=agent_config,
            eth_price_usd=2_500.0,
            fetched_at=ts,
        )
        cache.update(snapshot)

    path = OUT_DIR / "history_53a71d5.json"
    cache.save_to_file(str(path))
    _freeze_saved_at(path)
    return path


def make_base() -> Path:
    """Three tokens x six price points, plus the three overview series."""
    from maxpane_dashboard.data.base_cache import BaseTokenCache
    from maxpane_dashboard.data.base_models import BaseSnapshot, BaseToken

    def token(index: int, price: float) -> BaseToken:
        return BaseToken(
            address="0x" + f"{index:040x}",
            name=f"Token{index}",
            symbol=f"T{index}",
            price_usd=price,
            price_change_5m=None,
            price_change_1h=None,
            price_change_24h=None,
            volume_24h=1_000.0 * index,
            market_cap=10_000.0 * index,
            fdv=None,
            liquidity=5_000.0 * index,
            pair_address=None,
            dex="aerodrome",
            created_at=None,
        )

    cache = BaseTokenCache(max_history=120)
    for i in range(POINTS):
        ts = BASE_TS - (POINTS - 1 - i) * STEP
        snapshot = BaseSnapshot(
            trending_tokens=(
                token(1, 1.0 + i * 0.1),
                token(2, 20.0 + i * 0.5),
                token(3, 300.0 + i * 2.0),
            ),
            trending_pools=(),
            launches=(),
            fetched_at=ts,
        )
        cache.update(snapshot)
        cache.record_overview_point(
            timestamp=ts,
            total_volume=1_000_000.0 + i * 10_000.0,
            eth_price=2_500.0 + i * 5.0,
            trade_count=40_000 + i * 100,
        )

    path = OUT_DIR / "base_53a71d5.json"
    cache.save_to_file(str(path))
    _freeze_saved_at(path)
    return path


# ---------------------------------------------------------------------------
# WP-C: ocm + frenpet
# ---------------------------------------------------------------------------

# OCM polls every ~60s but its burn series is deliberately downsampled, so
# the fixture is built on a 30-minute cadence: eight updates spanning 3.5h,
# which is long enough for the hourly burn keepalive to fire and short
# enough to stay inside the 24h sparkline window.
OCM_STEP = 1_800.0
OCM_POINTS = 8

# ``burned_count`` per update.  Chosen so the fixture exercises every branch
# of ``_append_burn_sample``: a repeat inside the hour is dropped (i=1, 4, 6
# -- the dedupe-worthy repeats), a repeat an hour later is kept as the
# keepalive (i=2), and a change is kept immediately (i=3, 5, 7).  Five burn
# samples survive, against eight points in each of the other three series.
OCM_BURNED = (12, 12, 12, 13, 13, 14, 14, 15)


def make_ocm() -> Path:
    """Four series, a downsampled burn history and a non-zero holder count."""
    from maxpane_dashboard.data.ocm_cache import OCMCache
    from maxpane_dashboard.data.ocm_models import (
        OCMCollectionStats,
        OCMSnapshot,
        OCMStakingStats,
    )

    cache = OCMCache(max_history=120)
    for i in range(OCM_POINTS):
        ts = BASE_TS - (OCM_POINTS - 1 - i) * OCM_STEP
        total_supply = 4_000 + i
        burned = OCM_BURNED[i]
        snapshot = OCMSnapshot(
            fetched_at=ts,
            collection=OCMCollectionStats(
                total_supply=total_supply,
                max_supply=10_000,
                current_minting_cost=10 * 10**18,
                burned_count=burned,
                net_supply=total_supply - burned,
                remaining=10_000 - total_supply,
                minted_pct=total_supply / 100,
            ),
            staking=OCMStakingStats(
                # A different slope per series, so a round-trip that loaded
                # the wrong key could not pass.
                total_staked=1_500 + i * 10,
                ocmd_total_supply=5_000.0 + i * 100.0,
                daily_emission=1_500.0,
                staking_ratio=40.0,
                days_to_earn_mint=10.0,
            ),
            holder_count=0,
        )
        cache.update(snapshot)
    cache.update_holder_count(4_242)

    path = OUT_DIR / "ocm_53a71d5.json"
    cache.save_to_file(str(path))
    _freeze_saved_at(path)
    return path


def make_ocm_v1() -> Path:
    """The v2 fixture minus the two keys version 1 never had.

    Derived rather than generated: the pre-burn-series code is older than
    ``53a71d5`` and no longer exists in any tree this branch can check
    out, so the v1 file is produced from the v2 one by deleting exactly
    what version 1 did not write -- the ``version`` key itself (its
    absence is what ``payload.get(VERSION_KEY) or 1`` reads as 1) and
    ``burn_history``.  Every other key, and the key order, is untouched,
    which is precisely the shape ``test_ocm_cache.py``'s hand-written v1
    payloads describe.
    """
    payload = json.loads((OUT_DIR / "ocm_53a71d5.json").read_text())
    del payload["version"]
    del payload["burn_history"]
    path = OUT_DIR / "ocm_v1_53a71d5.json"
    path.write_text(json.dumps(payload))
    return path


FRENPET_POINTS = 6


def make_frenpet() -> Path:
    """Three pets x six score points, plus the three population series."""
    from maxpane_dashboard.data.frenpet_cache import FrenPetCache
    from maxpane_dashboard.data.frenpet_models import (
        FrenPet,
        FrenPetPopulation,
        FrenPetSnapshot,
    )

    def pet(pet_id: int, score: int) -> FrenPet:
        return FrenPet(
            id=pet_id,
            score=score,
            attack_points=100,
            defense_points=80,
            level=5,
            status=0,
            last_attacked=0,
            last_attack_used=0,
            shield_expires=0,
            time_until_starving=int(BASE_TS) + 86_400,
            staking_perks_until=0,
            wheel_last_spin=0,
            pet_wins=10,
            win_qty=10,
            loss_qty=5,
            shrooms=0,
            name=f"Pet{pet_id}",
            owner="0x" + "ab" * 20,
        )

    cache = FrenPetCache(max_history=120)
    for i in range(FRENPET_POINTS):
        ts = BASE_TS - (FRENPET_POINTS - 1 - i) * STEP
        # A different slope per pet, so a round-trip that loaded the wrong
        # key could not pass.
        pets = [
            pet(1, 10_000 + i * 100),
            pet(2, 20_000 + i * 200),
            pet(3, 30_000 + i * 300),
        ]
        population = FrenPetPopulation.from_pets(list(pets), now=ts)
        snapshot = FrenPetSnapshot(
            population=population,
            # Pets 1 and 2 are managed; pet 3 arrives via top_pets, which is
            # the other half of ``update``'s per-pet loop.
            managed_pets=(pets[0], pets[1]),
            top_pets=tuple(pets),
            fetched_at=ts,
        )
        cache.update(snapshot, battle_rate=float(20 + i))

    path = OUT_DIR / "frenpet_53a71d5.json"
    cache.save_to_file(str(path))
    _freeze_saved_at(path)
    return path


def make_frenpet_v1() -> Path:
    """The schema-2 fixture minus the four keys schema 1 never wrote.

    Same derivation as :func:`make_ocm_v1`: ``schema_version`` is deleted
    (a missing key reads as 1) along with the three population series,
    which is exactly what ``frenpet_cache.py``'s module docstring says a
    v1 file contains -- ``histories`` and nothing else.
    """
    payload = json.loads((OUT_DIR / "frenpet_53a71d5.json").read_text())
    del payload["schema_version"]
    for name in ("active_pets_history", "total_score_history", "battle_rate_history"):
        del payload[name]
    path = OUT_DIR / "frenpet_v1_53a71d5.json"
    path.write_text(json.dumps(payload))
    return path


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {sys.argv[0]} <path-to-53a71d5-worktree>")
    _require_worktree(sys.argv[1])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in (
        make_cattown(),
        make_dota(),
        make_bakery(),
        make_base(),
        make_ocm(),
        make_ocm_v1(),
        make_frenpet(),
        make_frenpet_v1(),
    ):
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
