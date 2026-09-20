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


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {sys.argv[0]} <path-to-53a71d5-worktree>")
    _require_worktree(sys.argv[1])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in (make_cattown(), make_dota(), make_bakery(), make_base()):
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
