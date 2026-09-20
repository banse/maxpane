"""FrenPetPerfScreen -- FrenPet performance dashboard as a Textual Screen.

Six of this screen's panels *compute* between the fetch and the dispatch, so
their ``PANELS`` rows are module-level adapters rather than
:func:`~maxpane_dashboard.screens.dashboard_screen.keys` rows. Each one is the
arithmetic that used to sit inside the screen's own ``try`` block, moved out
whole: same helpers, same order, same values.

**The clock is not injected here.** :func:`_perf_trends` samples ``time.time()``
for the single-point win-rate history, exactly as the hand-written block did.
That contradicts CLAUDE.md's "Inject the clock" and is a pre-existing hazard
this migration carried across rather than fixed -- filed as follow-up 19 in
``docs/handover_followups_2026_09.md``.
"""

from __future__ import annotations

import time

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from maxpane_dashboard.analytics.frenpet_perf_signals import (
    classify_avg_win_rate,
    classify_velocity,
    classify_weakest,
    compute_avg_win_rate,
    compute_total_velocity,
    find_weakest_pet,
    generate_perf_recommendation,
)
from maxpane_dashboard.screens.dashboard_screen import DashboardScreen
from maxpane_dashboard.widgets.address import address_text
from maxpane_dashboard.widgets.frenpet._chain import EXPLORER
from maxpane_dashboard.widgets.frenpet.perf import (
    FPPerfActivity,
    FPPerfHero,
    FPPerfPets,
    FPPerfSignals,
    FPPerfTrends,
    FPPerfVelocity,
)
from maxpane_dashboard.widgets.status_bar import StatusBar

#: Display budget for the wallet address in the title bar, excluding the
#: icon (``ICON_COLS``). No layout pin covers this hidden screen.
_WALLET_COLS = 11


def _perf_hero(data: dict) -> dict:
    """Wins, losses and score summed across the wallet's pets."""
    managed_pets = data.get("managed_pets", [])
    return {
        "total_wins": sum(p.win_qty for p in managed_pets),
        "total_losses": sum(p.loss_qty for p in managed_pets),
        "total_score": sum(float(p.score) for p in managed_pets),
        "avg_win_rate": compute_avg_win_rate(managed_pets),
        "pet_count": len(managed_pets),
    }


def _perf_pets(data: dict) -> dict:
    """The comparison table: one row per pet, plus the velocity map."""
    managed_pets = data.get("managed_pets", [])
    return {
        "pets": [
            {
                "id": p.id,
                "name": p.name,
                "score": p.score,
                "wins": p.win_qty,
                "losses": p.loss_qty,
                "atk": p.attack_points,
                "def": p.defense_points,
            }
            for p in managed_pets
        ],
        "pet_velocities": data.get("pet_velocities", {}),
    }


def _perf_trends(data: dict) -> dict:
    """The three sparklines, each derived rather than served.

    ``time.time()`` is sampled here for the one-point win-rate series; see this
    module's docstring (follow-up 19).
    """
    managed_pets = data.get("managed_pets", [])
    pet_score_histories = data.get("pet_score_histories", {})

    # Build aggregated score history from per-pet histories
    score_history: list[tuple[float, float]] = []
    if pet_score_histories:
        all_histories = list(pet_score_histories.values())
        if all_histories:
            ref = all_histories[0]
            for i, (ts, _val) in enumerate(ref):
                total = 0.0
                for hist in all_histories:
                    if i < len(hist):
                        total += hist[i][1]
                score_history.append((ts, total))

    # Velocity history: derive deltas from score history.
    # Expressed in points per DAY so the sparkline matches the
    # regression-based velocities shown elsewhere on this screen
    # (and on the wallet/pet views) instead of being 24x smaller.
    velocity_history: list[tuple[float, float]] = []
    if len(score_history) >= 2:
        for i in range(1, len(score_history)):
            ts = score_history[i][0]
            prev_ts = score_history[i - 1][0]
            delta_score = score_history[i][1] - score_history[i - 1][1]
            delta_time_days = (ts - prev_ts) / 86400.0
            if delta_time_days > 0:
                velocity_history.append((ts, delta_score / delta_time_days))

    # Win rate history: single point (no historical W/L data)
    total_wins = sum(p.win_qty for p in managed_pets)
    total_losses = sum(p.loss_qty for p in managed_pets)
    win_rate_history: list[tuple[float, float]] = []
    if (total_wins + total_losses) > 0:
        win_rate_history = [(time.time(), compute_avg_win_rate(managed_pets))]

    return {
        "score_history": score_history or None,
        "velocity_history": velocity_history or None,
        "win_rate_history": win_rate_history or None,
    }


def _perf_signals(data: dict) -> dict:
    """Average win rate, total velocity and the weakest pet, each classified."""
    managed_pets = data.get("managed_pets", [])
    avg_win_rate = compute_avg_win_rate(managed_pets)
    total_velocity = compute_total_velocity(data.get("pet_velocities", {}))
    wr_status, wr_color = classify_avg_win_rate(avg_win_rate)
    vel_status, vel_color = classify_velocity(total_velocity)

    weakest = find_weakest_pet(managed_pets)
    if weakest:
        weakest_name = weakest["name"]
        weakest_wr = weakest["win_rate"]
        weakest_status, weakest_color = classify_weakest(weakest_wr)
    else:
        weakest_name = "--"
        weakest_wr = 0.0
        weakest_status = "n/a"
        weakest_color = "dim"

    return {
        "avg_win_rate": avg_win_rate,
        "wr_status": wr_status,
        "wr_color": wr_color,
        "total_velocity": total_velocity,
        "vel_status": vel_status,
        "vel_color": vel_color,
        "weakest_name": weakest_name,
        "weakest_wr": weakest_wr,
        "weakest_status": weakest_status,
        "weakest_color": weakest_color,
        "recommendation": generate_perf_recommendation(
            avg_win_rate, total_velocity, weakest,
        ),
    }


def _perf_activity(data: dict) -> dict:
    """The wallet's own pets keyed by id, over the global name map."""
    managed_pets = data.get("managed_pets", [])
    full_names = dict(data.get("pet_names", {}))
    full_names.update({p.id: p.name for p in managed_pets})
    return {
        "recent_attacks": data.get("recent_attacks", []),
        "pet_ids": {p.id for p in managed_pets},
        "pet_names": full_names,
    }


def _perf_velocity(data: dict) -> dict:
    """Per-pet velocity sparklines: id and name only, plus the two maps."""
    managed_pets = data.get("managed_pets", [])
    return {
        "pets": [{"id": p.id, "name": p.name} for p in managed_pets],
        "pet_velocities": data.get("pet_velocities", {}),
        "pet_score_histories": data.get("pet_score_histories", {}),
    }


class FrenPetPerfScreen(DashboardScreen):
    """FrenPet performance dashboard: pet comparison, velocity, win rates."""

    #: The words the status bar shows for this dashboard.
    GAME_NAME = "frenpet performance"

    #: Worker name for the guarded refresh (see RefreshGuard).
    REFRESH_WORKER_NAME = "fpp-refresh"

    #: Transcribed from the six hand-written dispatch blocks, arithmetic for
    #: arithmetic; the status bar is updated by the base.
    PANELS = (
        (FPPerfHero, _perf_hero),
        (FPPerfPets, _perf_pets),
        (FPPerfTrends, _perf_trends),
        (FPPerfSignals, _perf_signals),
        (FPPerfActivity, _perf_activity),
        (FPPerfVelocity, _perf_velocity),
    )

    def compose(self) -> ComposeResult:
        yield Static(
            "FrenPet · Performance · Loading...",
            id="fpp-title",
        )

        yield FPPerfHero()

        with Horizontal(id="fpp-middle-row"):
            yield FPPerfPets()
            with Vertical(id="fpp-right-col"):
                yield FPPerfTrends()
                yield FPPerfSignals()

        yield Static("─" * 300, id="fpp-separator")

        with Horizontal(id="fpp-bottom-row"):
            yield FPPerfActivity()
            yield FPPerfVelocity()

        yield StatusBar()

    def _update_title(self, data: dict) -> None:
        # A Text, never a markup string: Static.update() defers markup
        # parsing into the message pump, and the icon's click action lives
        # in a Style that only survives outside markup parsing.
        title = self.query_one("#fpp-title", Static)
        wallet_addr = getattr(self._data_manager, "_wallet_address", "")
        pet_count = len(data.get("managed_pets", []))
        line = Text("FrenPet · Performance · ")
        if wallet_addr:
            line.append_text(address_text(wallet_addr, width=_WALLET_COLS, explorer=EXPLORER))
        else:
            line.append("?")
        line.append(f" · {pet_count} pets")
        title.update(line)
