"""FrenPetScreen -- FrenPet game dashboard (Overview-only mode)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from maxpane_dashboard.screens.dashboard_screen import DashboardScreen, keys
from maxpane_dashboard.widgets.frenpet.overview import (
    FPBattleActivity,
    FPBestPlays,
    FPGameSignals,
    FPOverviewHero,
    FPOverviewLeaderboard,
    FPScoreTrends,
)
from maxpane_dashboard.widgets.status_bar import StatusBar

#: FrenPet's genesis, the epoch the hero's age counts from. The manager does
#: not always carry it, and the hand-written dispatch block defaulted to this
#: literal; it moves here with the block, unchanged.
_GAME_START_TIMESTAMP = 1709251200


def _overview_hero(data: dict) -> dict:
    """The leader is the payload's own ``top_pet``, or the leaderboard's first."""
    top_pets = data.get("top_pets", [])
    return {
        "fp_reward_pool": data.get("fp_reward_pool", 0.0),
        "game_start_timestamp": data.get(
            "game_start_timestamp", _GAME_START_TIMESTAMP
        ),
        "top_pet": data.get("top_pet") or (top_pets[0] if top_pets else None),
    }


def _score_trends(data: dict) -> dict:
    """Population-level sparklines; ``score_histories`` renames its payload key."""
    return {
        "top_pets": data.get("top_pets", []),
        "score_histories": data.get("overview_score_histories", {}),
        "active_pets_history": data.get("active_pets_history"),
        "total_score_history": data.get("total_score_history"),
        "battle_rate_history": data.get("battle_rate_history"),
    }


def _game_signals(data: dict) -> dict:
    """Four global rates, each under a keyword of its own that is not its key."""
    return {
        "battle_rate": data.get("global_battle_rate", 0.0),
        "win_rate": data.get("global_win_rate", 50.0),
        "hibernation_rate": data.get("hibernation_rate", 0.0),
        "dominance": data.get("top_dominance", 1.0),
        "recommendation": data.get("overview_recommendation", ""),
    }


class FrenPetScreen(DashboardScreen):
    """FrenPet game dashboard (Overview only)."""

    #: The words the status bar shows for this dashboard.
    GAME_NAME = "frenpet"

    #: Worker name for the guarded refresh (see RefreshGuard).
    REFRESH_WORKER_NAME = "frenpet-refresh"

    #: Transcribed from the six hand-written dispatch blocks, default for
    #: default; the status bar is updated by the base. The leaderboard was the
    #: one positional call (``update_data(top_pets)``); its parameter is named
    #: ``top_pets``, so the keyword row is the same call.
    PANELS = (
        (FPOverviewHero, _overview_hero),
        (FPOverviewLeaderboard, keys("top_pets", top_pets=[])),
        (FPScoreTrends, _score_trends),
        (FPGameSignals, _game_signals),
        (
            FPBattleActivity,
            keys("recent_attacks", "pet_names", recent_attacks=[]),
        ),
        (
            FPBestPlays,
            keys("top_earners", "rising_stars", top_earners=[], rising_stars=[]),
        ),
    )

    def compose(self) -> ComposeResult:
        yield Static("FrenPet · Overview", id="title-bar")
        yield FPOverviewHero()
        with Horizontal(id="middle-row"):
            yield FPOverviewLeaderboard()
            with Vertical(id="right-col"):
                yield FPScoreTrends()
                yield FPGameSignals()
        yield Static("─" * 300, id="separator")
        with Horizontal(id="bottom-row"):
            yield FPBattleActivity()
            yield FPBestPlays()
        yield StatusBar()

    def _update_title(self, data: dict) -> None:
        title = self.query_one("#title-bar", Static)
        population_stats = data.get("population_stats", {})
        # Keys are "total"/"active": that is what
        # calculate_population_stats returns and what the manager's
        # _safe_call fallback defaults to.  Nothing in the repo ever
        # produced "total_pets"/"active_pets", so this header used to
        # be permanently stuck on the bare "FrenPet · Overview".
        total = population_stats.get("total", 0)
        active = population_stats.get("active", 0)
        if total:
            title.update(
                f"FrenPet · Overview · {active}/{total} active"
            )
        else:
            title.update("FrenPet · Overview")
