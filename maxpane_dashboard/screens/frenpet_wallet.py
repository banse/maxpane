"""FrenPetWalletScreen -- FrenPet wallet-level dashboard as a Textual Screen."""

from __future__ import annotations

import logging
import time

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from maxpane_dashboard.analytics.frenpet_wallet_signals import (
    classify_fp_rate,
    classify_pool_share,
    classify_win_rate,
    compute_pool_share,
    compute_win_rate,
    find_most_efficient,
    find_top_earner,
    generate_wallet_recommendation,
)
from maxpane_dashboard.data.frenpet_manager import FrenPetManager
from maxpane_dashboard.widgets.frenpet.wallet import (
    FPWalletActivity,
    FPWalletBestPlays,
    FPWalletHero,
    FPWalletPets,
    FPWalletSignals,
    FPWalletTrends,
)
from maxpane_dashboard.widgets.status_bar import StatusBar

logger = logging.getLogger(__name__)


def _short_addr(address: str) -> str:
    """Shorten a hex address to 0x030A...4A51 format."""
    if len(address) > 10:
        return f"{address[:6]}...{address[-4:]}"
    return address


class FrenPetWalletScreen(Screen):
    """FrenPet wallet-level dashboard: ETH rewards, pool share, APR."""

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
            "FrenPet \u00b7 Wallet \u00b7 Loading...",
            id="fpw-title",
        )

        yield FPWalletHero()

        with Horizontal(id="fpw-middle-row"):
            yield FPWalletPets()
            with Vertical(id="fpw-right-col"):
                yield FPWalletTrends()
                yield FPWalletSignals()

        yield Static("\u2500" * 300, id="fpw-separator")

        with Horizontal(id="fpw-bottom-row"):
            yield FPWalletActivity()
            yield FPWalletBestPlays()

        yield StatusBar()

    def on_screen_resume(self) -> None:
        self._do_initial_refresh()
        self._refresh_timer = self.set_interval(
            self._poll_interval, self._schedule_refresh
        )
        try:
            self.query_one(StatusBar).set_theme_name(self.app.theme)
            self.query_one(StatusBar).set_game_name("frenpet wallet")
        except Exception:
            pass

    def on_screen_suspend(self) -> None:
        if self._refresh_timer:
            self._refresh_timer.stop()
            self._refresh_timer = None

    def _do_initial_refresh(self) -> None:
        self.run_worker(self._do_refresh(), exclusive=True, name="fpw-refresh")

    def _schedule_refresh(self) -> None:
        self.run_worker(self._do_refresh(), exclusive=True, name="fpw-refresh")

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
        wallet_rewards = data.get("wallet_rewards")
        pet_names = data.get("pet_names", {})
        pet_score_histories = data.get("pet_score_histories", {})
        recent_attacks = data.get("recent_attacks", [])

        # -- Title bar ---------------------------------------------------------
        try:
            title = self.query_one("#fpw-title", Static)
            wallet_addr = getattr(self._data_manager, "_wallet_address", "")
            short = _short_addr(wallet_addr) if wallet_addr else "?"
            pet_count = len(managed_pets)
            title.update(
                f"FrenPet \u00b7 Wallet \u00b7 {short} \u00b7 {pet_count} pets"
            )
        except Exception:
            pass

        # -- Hero metrics ------------------------------------------------------
        try:
            if wallet_rewards:
                total_eth_wei = wallet_rewards.get("total_eth_wei", 0)
                eth_price_usd = wallet_rewards.get("eth_price_usd", 0.0)
                user_shares = wallet_rewards.get("user_shares", 0)
                total_shares = wallet_rewards.get("total_shares", 0)
                total_fp_in_pool = wallet_rewards.get("total_fp_in_pool", 0)
                pool_share_pct = wallet_rewards.get("pool_share_pct", 0.0)

                # Compute APR from wallet_rewards data
                apr = wallet_rewards.get("apr", 0.0)

                self.query_one(FPWalletHero).update_data(
                    total_eth_wei=total_eth_wei,
                    eth_price_usd=eth_price_usd,
                    pool_share_pct=pool_share_pct,
                    total_fp_in_pool=total_fp_in_pool,
                    apr=apr,
                    user_shares=user_shares,
                    pet_count=len(managed_pets),
                )
            else:
                self.query_one(FPWalletHero).update_data(
                    total_eth_wei=0,
                    eth_price_usd=0.0,
                    pool_share_pct=0.0,
                    total_fp_in_pool=0,
                    apr=0.0,
                    user_shares=0,
                    pet_count=len(managed_pets),
                )
        except Exception as exc:
            logger.debug("Failed to update FPWalletHero: %s", exc)

        # -- Pets table --------------------------------------------------------
        try:
            pet_rewards_map = (
                wallet_rewards.get("pet_rewards", {}) if wallet_rewards else {}
            )
            pets_for_table = []
            for pet in managed_pets:
                pr = pet_rewards_map.get(pet.id, {})
                pets_for_table.append({
                    "id": pet.id,
                    "name": pet.name,
                    "score": pet.score,
                    "wins": pet.win_qty,
                    "losses": pet.loss_qty,
                    "atk": pet.attack_points,
                    "def": pet.defense_points,
                    "pending_eth_wei": pr.get("pending_eth_wei", 0)
                    + pr.get("eth_owed_wei", 0),
                })
            self.query_one(FPWalletPets).update_data(pets_for_table)
        except Exception as exc:
            logger.debug("Failed to update FPWalletPets: %s", exc)

        # -- Trends (sparklines) -----------------------------------------------
        try:
            # Build aggregated score history from per-pet histories
            score_history: list[tuple[float, float]] = []
            if pet_score_histories:
                # Sum scores across all pets at each timestamp
                # Use the first pet's timestamps as reference
                all_histories = list(pet_score_histories.values())
                if all_histories:
                    ref = all_histories[0]
                    for i, (ts, _val) in enumerate(ref):
                        total = 0.0
                        for hist in all_histories:
                            if i < len(hist):
                                total += hist[i][1]
                        score_history.append((ts, total))

            # ETH rewards history -- we only have the current value,
            # so build a single-point series or use None
            eth_total_wei = (
                wallet_rewards.get("total_eth_wei", 0) if wallet_rewards else 0
            )
            eth_history: list[tuple[float, float]] = [
                (time.time(), eth_total_wei / 1e18)
            ] if eth_total_wei > 0 else []

            # Win rate history -- single point from current data
            total_wins = sum(p.win_qty for p in managed_pets)
            total_losses = sum(p.loss_qty for p in managed_pets)
            wr = compute_win_rate(total_wins, total_losses)
            win_rate_history: list[tuple[float, float]] = [
                (time.time(), wr)
            ] if (total_wins + total_losses) > 0 else []

            self.query_one(FPWalletTrends).update_data(
                score_history=score_history or None,
                eth_history=eth_history or None,
                win_rate_history=win_rate_history or None,
            )
        except Exception as exc:
            logger.debug("Failed to update FPWalletTrends: %s", exc)

        # -- Signals -----------------------------------------------------------
        try:
            total_fp_per_second_raw = (
                wallet_rewards.get("total_fp_per_second", 0) if wallet_rewards else 0
            )
            # Convert from wei (18 decimals) to human-readable FP
            total_fp_per_second = total_fp_per_second_raw / 1e18
            fp_status, fp_color = classify_fp_rate(total_fp_per_second_raw)

            total_wins = sum(p.win_qty for p in managed_pets)
            total_losses = sum(p.loss_qty for p in managed_pets)
            win_rate = compute_win_rate(total_wins, total_losses)
            win_status, win_color = classify_win_rate(win_rate)

            pool_share_pct = (
                wallet_rewards.get("pool_share_pct", 0.0) if wallet_rewards else 0.0
            )
            pool_status, pool_color = classify_pool_share(pool_share_pct)

            total_eth_wei = (
                wallet_rewards.get("total_eth_wei", 0) if wallet_rewards else 0
            )
            recommendation = generate_wallet_recommendation(
                pool_share_pct, win_rate, total_fp_per_second_raw, total_eth_wei,
            )

            self.query_one(FPWalletSignals).update_data(
                fp_per_second=total_fp_per_second,
                fp_status=fp_status,
                fp_color=fp_color,
                win_rate=win_rate,
                win_status=win_status,
                win_color=win_color,
                pool_share=pool_share_pct,
                pool_status=pool_status,
                pool_color=pool_color,
                recommendation=recommendation,
            )
        except Exception as exc:
            logger.debug("Failed to update FPWalletSignals: %s", exc)

        # -- Activity feed -----------------------------------------------------
        try:
            pet_ids = {p.id for p in managed_pets}
            pet_name_map = {p.id: p.name for p in managed_pets}
            # Merge with global pet_names for opponent resolution
            full_names = dict(pet_names)
            full_names.update(pet_name_map)

            self.query_one(FPWalletActivity).update_data(
                recent_attacks=recent_attacks,
                pet_ids=pet_ids,
                pet_names=full_names,
            )
        except Exception as exc:
            logger.debug("Failed to update FPWalletActivity: %s", exc)

        # -- Best plays --------------------------------------------------------
        try:
            pets_for_analytics = [
                {
                    "name": p.name,
                    "score": p.score,
                    "wins": p.win_qty,
                    "losses": p.loss_qty,
                }
                for p in managed_pets
            ]
            top_earner = find_top_earner(pets_for_analytics)
            most_efficient = find_most_efficient(pets_for_analytics)

            self.query_one(FPWalletBestPlays).update_data(
                top_earner=top_earner,
                most_efficient=most_efficient,
            )
        except Exception as exc:
            logger.debug("Failed to update FPWalletBestPlays: %s", exc)

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
        self.run_worker(self._do_refresh(), exclusive=True, name="fpw-refresh")
