"""TTTScreen -- Ten Thousand Tokens dashboard as a Textual Screen."""

from __future__ import annotations

import logging

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from maxpane_dashboard.data.ttt_manager import TTTManager
from maxpane_dashboard.widgets.status_bar import StatusBar
from maxpane_dashboard.widgets.ttt import (
    TTTActivityFeed,
    TTTClaimsTable,
    TTTFeesTable,
    TTTHeroMetrics,
    TTTLeaderboard,
    TTTSignals,
    TTTSparkline,
)

logger = logging.getLogger(__name__)


class TTTScreen(Screen):
    """Ten Thousand Tokens dashboard.

    Mirrors the layout pattern used by :class:`OCMScreen` but adds a
    Fees/Claims toggle (``c`` key) since the bottom-right slot serves two
    complementary tables.
    """

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=False),
        Binding("c", "toggle_view", "Toggle Fees/Claims", show=True),
    ]

    def __init__(
        self,
        data_manager: TTTManager,
        poll_interval: int = 30,
        name: str = "ttt",
        **kwargs,
    ):
        super().__init__(name=name, **kwargs)
        self._data_manager = data_manager
        self._poll_interval = poll_interval
        self._refresh_timer = None
        self._active_view: str = "fees"  # or "claims"

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Static(
            "Ten Thousand Tokens · Ethereum Mainnet · 0/10,000",
            id="title-bar",
        )

        yield TTTHeroMetrics()

        with Horizontal(id="middle-row"):
            yield TTTLeaderboard()
            with Vertical(id="right-col"):
                yield TTTSparkline()
                yield TTTSignals()

        yield Static("─" * 300, id="separator")

        with Horizontal(id="bottom-row"):
            yield TTTActivityFeed()
            # Both tables live in the layout; one is hidden at a time.
            yield TTTFeesTable(id="ttt-fees-table")
            yield TTTClaimsTable(id="ttt-claims-table")

        yield StatusBar()

    def on_mount(self) -> None:
        # Start with Fees visible, Claims hidden.
        try:
            self.query_one("#ttt-claims-table").display = False
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Actions / bindings
    # ------------------------------------------------------------------

    def action_refresh(self) -> None:
        self.run_worker(self._do_refresh(), exclusive=True, name="ttt-refresh")

    def action_toggle_view(self) -> None:
        if self._active_view == "fees":
            self._active_view = "claims"
            try:
                self.query_one("#ttt-fees-table").display = False
                self.query_one("#ttt-claims-table").display = True
            except Exception:
                pass
        else:
            self._active_view = "fees"
            try:
                self.query_one("#ttt-fees-table").display = True
                self.query_one("#ttt-claims-table").display = False
            except Exception:
                pass
        try:
            self.query_one(StatusBar).set_active_view(self._active_view)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_screen_resume(self) -> None:
        self._do_initial_refresh()
        self._refresh_timer = self.set_interval(
            self._poll_interval, self._schedule_refresh
        )
        try:
            self.query_one(StatusBar).set_theme_name(self.app.theme)
            self.query_one(StatusBar).set_game_name("ten thousand tokens")
            self.query_one(StatusBar).set_active_view(self._active_view)
        except Exception:
            pass

    def on_screen_suspend(self) -> None:
        if self._refresh_timer:
            self._refresh_timer.stop()
            self._refresh_timer = None

    # ------------------------------------------------------------------
    # Refresh flow
    # ------------------------------------------------------------------

    def _do_initial_refresh(self) -> None:
        self.run_worker(self._do_refresh(), exclusive=True, name="ttt-refresh")

    def _schedule_refresh(self) -> None:
        self.run_worker(self._do_refresh(), exclusive=True, name="ttt-refresh")

    async def _do_refresh(self) -> None:
        try:
            data = await self._data_manager.fetch_and_compute()
        except Exception as exc:
            logger.debug("TTT refresh failed: %s", exc)
            try:
                self.query_one(StatusBar).update_data(
                    last_updated_seconds_ago=999,
                    error_count=getattr(self._data_manager, "_error_count", 0),
                    poll_interval=self._poll_interval,
                )
            except Exception:
                pass
            return

        # Title bar
        try:
            launches = data.get("launches", 0) or 0
            max_supply = data.get("max_supply", 10_000) or 10_000
            self.query_one("#title-bar", Static).update(
                f"Ten Thousand Tokens · Ethereum Mainnet · "
                f"{launches}/{max_supply:,}"
            )
        except Exception as exc:
            logger.debug("Failed to update title bar: %s", exc)

        # Hero metrics
        try:
            self.query_one(TTTHeroMetrics).update_data(
                unburned=data.get("unburned"),
                burned_pct=data.get("burned_pct"),
                launches=data.get("launches"),
                launches_24h=data.get("launches_24h"),
                holder_pool_eth_total=data.get("holder_pool_eth_total"),
                holder_pool_eth_24h=data.get("holder_pool_eth_24h"),
                total_mcap_usd=data.get("total_mcap_usd"),
                total_mcap_eth=data.get("total_mcap_eth"),
                total_mcap_token_count=data.get("total_mcap_token_count"),
            )
        except Exception as exc:
            logger.debug("Failed to update TTTHeroMetrics: %s", exc)

        # Leaderboard
        try:
            self.query_one(TTTLeaderboard).update_data(
                top_tokens_by_volume=data.get("top_tokens_by_volume"),
            )
        except Exception as exc:
            logger.debug("Failed to update TTTLeaderboard: %s", exc)

        # Sparkline
        try:
            self.query_one(TTTSparkline).update_data(
                burns_history=data.get("burns_history"),
                volume_history=data.get("volume_history", []),
            )
        except Exception as exc:
            logger.debug("Failed to update TTTSparkline: %s", exc)

        # Signals
        try:
            self.query_one(TTTSignals).update_data(
                fresh_launch_signal=data.get("fresh_launch_signal"),
                buybacks_ready_signal=data.get("buybacks_ready_signal"),
                decay_window_signal=data.get("decay_window_signal"),
                concentration_signal=data.get("concentration_signal"),
            )
        except Exception as exc:
            logger.debug("Failed to update TTTSignals: %s", exc)

        # Activity feed
        try:
            self.query_one(TTTActivityFeed).update_data(
                activity_events=data.get("activity_events"),
            )
        except Exception as exc:
            logger.debug("Failed to update TTTActivityFeed: %s", exc)

        # Fees table (bottom-right α)
        try:
            self.query_one(TTTFeesTable).update_data(
                top_fee_engines=data.get("top_fee_engines"),
            )
        except Exception as exc:
            logger.debug("Failed to update TTTFeesTable: %s", exc)

        # Claims table (bottom-right γ)
        try:
            self.query_one(TTTClaimsTable).update_data(
                claim_math_scenarios=data.get("claim_math_scenarios"),
            )
        except Exception as exc:
            logger.debug("Failed to update TTTClaimsTable: %s", exc)

        # Status bar
        try:
            self.query_one(StatusBar).update_data(
                last_updated_seconds_ago=data.get("last_updated_seconds_ago", 0),
                error_count=data.get("error_count", 0),
                poll_interval=data.get("poll_interval", self._poll_interval),
            )
        except Exception as exc:
            logger.debug("Failed to update StatusBar: %s", exc)
