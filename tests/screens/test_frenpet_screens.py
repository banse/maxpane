"""Headless Textual tests for the CLI-only FrenPet screens.

Both screens are driven with a fake manager that returns the real
``FrenPetManager.fetch_and_compute()`` contract (no network), then we
assert the two defects these screens shipped with stay fixed:

* ``frenpet_full`` Pet view read ``all_scores`` / ``population_pets`` --
  keys the manager never produced -- so it always showed "Rank #0 of 0"
  and "No viable targets" (MEDI-32);
* ``frenpet_wallet`` passed raw 18-decimal ``uint256`` pool figures to a
  display formatter, printing garbage like "37325669265659.0B FP pool"
  (MEDI-33).
"""

from __future__ import annotations

import time

import pytest
from textual.app import App
from textual.widgets import DataTable, Static

from maxpane_dashboard.data.frenpet_models import FrenPet
from maxpane_dashboard.screens.frenpet_full import FrenPetFullScreen
from maxpane_dashboard.screens.frenpet_wallet import FrenPetWalletScreen
from maxpane_dashboard.widgets.frenpet import PetSignals, SniperQueue
from maxpane_dashboard.widgets.frenpet.wallet import FPWalletHero


def _make_pet(pet_id: int, score: int, **overrides) -> FrenPet:
    now = int(time.time())
    defaults = dict(
        id=pet_id,
        score=score,
        attack_points=300,
        defense_points=50,
        level=5,
        status=0,
        last_attacked=0,
        last_attack_used=0,
        shield_expires=0,
        time_until_starving=now + 86_400 * 3,
        staking_perks_until=0,
        wheel_last_spin=0,
        pet_wins=20,
        win_qty=20,
        loss_qty=10,
        shrooms=0,
        name=f"Pet{pet_id}",
        owner="0xabc",
    )
    defaults.update(overrides)
    return FrenPet(**defaults)  # type: ignore[arg-type]


def _sample_data() -> dict:
    mine = _make_pet(1, 100_000)
    population = [
        mine,
        _make_pet(2, 90_000, owner="0xother"),
        _make_pet(3, 80_000, owner="0xother"),
        _make_pet(4, 70_000, owner="0xother"),
    ]
    return {
        "population_stats": {"total": 4, "active": 4, "hibernated": 0,
                             "avg_score": 85_000.0, "median_score": 85_000.0,
                             "avg_atk": 300.0, "avg_def": 50.0,
                             "total_score": 340_000.0},
        "score_distribution": {},
        "top_pets": population,
        "recent_attacks": [],
        "global_battle_rate": 0.0,
        "managed_pets": [mine],
        "total_score": 100_000.0,
        "combined_win_rate": 66.6,
        "pet_score_histories": {1: [(1.0, 90_000.0), (2.0, 100_000.0)]},
        "alerts": [],
        "pet_evaluations": {1: {"name": "Pet1", "rank": 1, "phase": "Adult",
                                "tod_status": {"hours_remaining": 72.0,
                                               "status": "safe",
                                               "color": "green"},
                                "battle_efficiency": 66.6, "velocity": 2400.0}},
        "market_conditions": {"available_targets": 3, "sweet_spot_count": 3,
                              "avg_opponent_def": 50.0, "hibernation_rate": 0.0,
                              "shield_rate": 0.0, "target_density": "high",
                              "verdict": "aggressive"},
        "threat_levels": {1: {"threat_count": 0, "threat_level": "low"}},
        "population_pets": population,
        "pet_velocities": {1: 2400.0},
        "pet_ranks": {1: {"rank": 1, "total": 4, "percentile": 100.0,
                          "distance_to_next": 0.0,
                          "distance_from_prev": 10_000.0}},
        "fp_reward_pool": 1.0,
        "game_start_timestamp": 1709251200,
        "top_pet": population[0],
        "overview_total_score": 340_000.0,
        "global_win_rate": 50.0,
        "shield_rate": 0.0,
        "top_dominance": 1.1,
        "overview_recommendation": "",
        "top_earners": [],
        "rising_stars": [],
        "overview_score_histories": {},
        "active_pets_history": [],
        "total_score_history": [],
        "battle_rate_history": [],
        "pet_names": {p.id: p.name for p in population},
        "wallet_rewards": {
            "pet_rewards": {1: {"pending_eth_wei": 5 * 10**16,
                                "eth_owed_wei": 0,
                                "fp_per_second": 10**15}},
            "total_pending_eth_wei": 5 * 10**16,
            "total_eth_owed_wei": 0,
            "total_eth_wei": 5 * 10**16,
            "total_fp_per_second": 10**15,
            # Live values, unscaled: userShares() and totalFpInPool()
            # both return 18-decimal uint256.
            "user_shares": 1_234 * 10**18,
            "total_shares": 4_936 * 10**18,
            "total_fp_in_pool": 37_325 * 10**18,
            "pool_share_pct": 25.0,
            "eth_price_usd": 3000.0,
        },
        "error_count": 0,
        "last_updated_seconds_ago": 1.0,
        "poll_interval": 30,
    }


class _FakeManager:
    """Stand-in for FrenPetManager that never touches the network."""

    def __init__(self) -> None:
        self._error_count = 0
        self._wallet_address = "0x030A000000000000000000000000000000004A51"
        self.calls = 0

    async def fetch_and_compute(self) -> dict:
        self.calls += 1
        return _sample_data()

    async def close(self) -> None:
        pass


class _Harness(App):
    def __init__(self, screen) -> None:
        super().__init__()
        self._screen = screen

    def on_mount(self) -> None:
        self.push_screen(self._screen)


def _text(widget, selector: str) -> str:
    content = widget.query_one(selector, Static).content
    return str(getattr(content, "plain", content))


# ---------------------------------------------------------------------------
# frenpet_full Pet view (MEDI-32)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pet_view_shows_real_rank_and_targets() -> None:
    manager = _FakeManager()
    screen = FrenPetFullScreen(manager, poll_interval=30, name="frenpet_full")
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen.update_pet_view(_sample_data())
        await pilot.pause()

        signals = screen.query_one(PetSignals)
        rank_line = _text(signals, "#psig-rank")
        # Rank comes from the manager's pet_ranks, not from a key that
        # nothing produces: "#1 of 4", never "#0 of 0".
        assert "#1" in rank_line
        assert "of 4" in rank_line
        assert "#0 of 0" not in rank_line

        # The sniper queue receives the population and finds targets.
        table = screen.query_one(SniperQueue).query_one("#sq-table", DataTable)
        assert table.row_count >= 1
        first_row = [str(c) for c in table.get_row_at(0)]
        assert not any("No viable targets" in c for c in first_row)


@pytest.mark.asyncio
async def test_pet_view_survives_missing_optional_keys() -> None:
    """A payload without ranks/population still renders the placeholder."""
    manager = _FakeManager()
    screen = FrenPetFullScreen(manager, poll_interval=30, name="frenpet_full")
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        data = _sample_data()
        data.pop("pet_ranks")
        data.pop("population_pets")
        screen.update_pet_view(data)
        await pilot.pause()

        table = screen.query_one(SniperQueue).query_one("#sq-table", DataTable)
        first_row = [str(c) for c in table.get_row_at(0)]
        assert any("No viable targets" in c for c in first_row)


# ---------------------------------------------------------------------------
# frenpet_wallet hero (MEDI-33)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_wallet_hero_scales_pool_figures_from_wei() -> None:
    manager = _FakeManager()
    screen = FrenPetWalletScreen(manager, poll_interval=30, name="frenpet_wallet")
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()

        hero = screen.query_one(FPWalletHero)
        pool_text = _text(hero, "#fpw-hero-pool")
        apr_text = _text(hero, "#fpw-hero-apr")

        # 37,325e18 wei == 37.3K FP, not 37325669265659.0B.
        assert "37.3K FP pool" in pool_text
        assert "B FP" not in pool_text
        assert "1.2K FP staked" in apr_text
        assert "B FP" not in apr_text
