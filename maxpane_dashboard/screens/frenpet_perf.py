"""FrenPetPerfScreen -- FrenPet performance dashboard as a Textual Screen."""

from __future__ import annotations

import logging
import time

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
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
from maxpane_dashboard.data.frenpet_manager import FrenPetManager
from maxpane_dashboard.widgets.frenpet.perf import (
    FPPerfActivity,
    FPPerfHero,
    FPPerfPets,
    FPPerfSignals,
    FPPerfTrends,
    FPPerfVelocity,
)
from maxpane_dashboard.widgets.status_bar import StatusBar

logger = logging.getLogger(__name__)


def _short_addr(address: str) -> str:
    """Shorten a hex address to 0x030A...4A51 format."""
    if len(address) > 10:
        return f"{address[:6]}...{address[-4:]}"
    return address


class FrenPetPerfScreen(Screen):
    """FrenPet performance dashboard: pet comparison, velocity, win rates."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=False),
    ]

    def __init__(self, data_manager: FrenPetManager, poll_interval: int, **kwargs):
        super().__init__(**kwargs)
        self._data_manager = data_manager
        self._poll_interval = poll_interval
        self._refresh_timer = None

    def compose(self) -> ComposeResult:
        yield Static(
            "FrenPet \u00b7 Performance \u00b7 Loading...",
            id="fpp-title",
        )

        yield FPPerfHero()

        with Horizontal(id="fpp-middle-row"):
            yield FPPerfPets()
            with Vertical(id="fpp-right-col"):
                yield FPPerfTrends()
                yield FPPerfSignals()

        yield Static("\u2500" * 300, id="fpp-separator")

        with Horizontal(id="fpp-bottom-row"):
            yield FPPerfActivity()
            yield FPPerfVelocity()

        yield StatusBar()

    def on_screen_resume(self) -> None:
        self._do_initial_refresh()
        self._refresh_timer = self.set_interval(
            self._poll_interval, self._schedule_refresh
        )
        try:
            self.query_one(StatusBar).set_theme_name(self.app.theme)
            self.query_one(StatusBar).set_game_name("frenpet performance")
        except Exception:
            pass

    def on_screen_suspend(self) -> None:
        if self._refresh_timer:
            self._refresh_timer.stop()
            self._refresh_timer = None

    def _do_initial_refresh(self) -> None:
        self.run_worker(self._do_refresh(), exclusive=True, name="fpp-refresh")

    def _schedule_refresh(self) -> None:
        self.run_worker(self._do_refresh(), exclusive=True, name="fpp-refresh")

    async def _do_refresh(self) -> None:
        try:
            data = await self._data_manager.fetch_and_compute()
        except Exception as exc:
            logger.debug("Refresh failed: %s", exc)
            try:
                self.query_one(StatusBar).update_data(
                    last_updated_seconds_ago=999,
                    error_count=getattr(self._data_manager, "_error_count", 0),
                    poll_interval=self._poll_interval,
                )
            except Exception:
                pass
            return

        managed_pets = data.get("managed_pets", [])
        pet_velocities = data.get("pet_velocities", {})
        pet_score_histories = data.get("pet_score_histories", {})
        recent_attacks = data.get("recent_attacks", [])
        pet_names = data.get("pet_names", {})

        # -- Title bar ---------------------------------------------------------
        try:
            title = self.query_one("#fpp-title", Static)
            wallet_addr = getattr(self._data_manager, "_wallet_address", "")
            short = _short_addr(wallet_addr) if wallet_addr else "?"
            pet_count = len(managed_pets)
            title.update(
                f"FrenPet \u00b7 Performance \u00b7 {short} \u00b7 {pet_count} pets"
            )
        except Exception:
            pass

        # -- Aggregate metrics -------------------------------------------------
        total_wins = sum(p.win_qty for p in managed_pets)
        total_losses = sum(p.loss_qty for p in managed_pets)
        total_score = sum(float(p.score) for p in managed_pets)
        avg_win_rate = compute_avg_win_rate(managed_pets)

        # -- Hero metrics ------------------------------------------------------
        try:
            self.query_one(FPPerfHero).update_data(
                total_wins=total_wins,
                total_losses=total_losses,
                total_score=total_score,
                avg_win_rate=avg_win_rate,
                pet_count=len(managed_pets),
            )
        except Exception as exc:
            logger.debug("Failed to update FPPerfHero: %s", exc)

        # -- Pet comparison table ----------------------------------------------
        try:
            pets_for_table = [
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
            ]
            self.query_one(FPPerfPets).update_data(
                pets=pets_for_table,
                pet_velocities=pet_velocities,
            )
        except Exception as exc:
            logger.debug("Failed to update FPPerfPets: %s", exc)

        # -- Trends (sparklines) -----------------------------------------------
        try:
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

            # Velocity history: derive deltas from score history
            velocity_history: list[tuple[float, float]] = []
            if len(score_history) >= 2:
                for i in range(1, len(score_history)):
                    ts = score_history[i][0]
                    prev_ts = score_history[i - 1][0]
                    delta_score = score_history[i][1] - score_history[i - 1][1]
                    delta_time_hr = (ts - prev_ts) / 3600.0
                    if delta_time_hr > 0:
                        velocity_history.append((ts, delta_score / delta_time_hr))

            # Win rate history: single point (no historical W/L data)
            win_rate_history: list[tuple[float, float]] = []
            if (total_wins + total_losses) > 0:
                win_rate_history = [(time.time(), avg_win_rate)]

            self.query_one(FPPerfTrends).update_data(
                score_history=score_history or None,
                velocity_history=velocity_history or None,
                win_rate_history=win_rate_history or None,
            )
        except Exception as exc:
            logger.debug("Failed to update FPPerfTrends: %s", exc)

        # -- Signals -----------------------------------------------------------
        try:
            total_velocity = compute_total_velocity(pet_velocities)
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

            recommendation = generate_perf_recommendation(
                avg_win_rate, total_velocity, weakest,
            )

            self.query_one(FPPerfSignals).update_data(
                avg_win_rate=avg_win_rate,
                wr_status=wr_status,
                wr_color=wr_color,
                total_velocity=total_velocity,
                vel_status=vel_status,
                vel_color=vel_color,
                weakest_name=weakest_name,
                weakest_wr=weakest_wr,
                weakest_status=weakest_status,
                weakest_color=weakest_color,
                recommendation=recommendation,
            )
        except Exception as exc:
            logger.debug("Failed to update FPPerfSignals: %s", exc)

        # -- Activity feed -----------------------------------------------------
        try:
            pet_ids = {p.id for p in managed_pets}
            pet_name_map = {p.id: p.name for p in managed_pets}
            full_names = dict(pet_names)
            full_names.update(pet_name_map)

            self.query_one(FPPerfActivity).update_data(
                recent_attacks=recent_attacks,
                pet_ids=pet_ids,
                pet_names=full_names,
            )
        except Exception as exc:
            logger.debug("Failed to update FPPerfActivity: %s", exc)

        # -- Pet velocity sparklines -------------------------------------------
        try:
            pets_for_velocity = [
                {
                    "id": p.id,
                    "name": p.name,
                }
                for p in managed_pets
            ]
            self.query_one(FPPerfVelocity).update_data(
                pets=pets_for_velocity,
                pet_velocities=pet_velocities,
                pet_score_histories=pet_score_histories,
            )
        except Exception as exc:
            logger.debug("Failed to update FPPerfVelocity: %s", exc)

        # -- Status bar --------------------------------------------------------
        try:
            self.query_one(StatusBar).update_data(
                last_updated_seconds_ago=data.get("last_updated_seconds_ago", 0),
                error_count=data.get("error_count", 0),
                poll_interval=data.get("poll_interval", self._poll_interval),
            )
        except Exception as exc:
            logger.debug("Failed to update StatusBar: %s", exc)

    def action_refresh(self) -> None:
        self.run_worker(self._do_refresh(), exclusive=True, name="fpp-refresh")
