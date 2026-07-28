"""TalismansScreen -- Talismans NFT dashboard as a Textual Screen."""

from __future__ import annotations

import logging

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from maxpane_dashboard.data.talismans_manager import TalismansManager
from maxpane_dashboard.screens.refresh_guard import RefreshGuard
from maxpane_dashboard.widgets.status_bar import StatusBar
from maxpane_dashboard.widgets.talismans import (
    TalismansActivityFeed,
    TalismansHeroMetrics,
    TalismansLeaderboard,
    TalismansMaterialsTable,
    TalismansMatrixTable,
    TalismansSignals,
    TalismansSparkline,
)

logger = logging.getLogger(__name__)


class TalismansScreen(RefreshGuard, Screen):
    """Talismans core-conservation NFT dashboard.

    Mirrors the layout pattern used by :class:`TTTScreen` but adds a
    Matrix/Materials toggle (``c`` key) since the bottom-right slot serves
    two complementary tables.
    """

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=False),
        Binding("c", "toggle_view", "Matrix/Materials", show=True),
    ]

    #: Worker name for the guarded refresh (see RefreshGuard).
    REFRESH_WORKER_NAME = "talismans-refresh"

    def __init__(
        self,
        data_manager: TalismansManager,
        poll_interval: int = 30,
        name: str = "talismans",
        **kwargs,
    ):
        super().__init__(name=name, **kwargs)
        self._data_manager = data_manager
        self._poll_interval = poll_interval
        self._refresh_timer = None
        self._active_view: str = "matrix"  # or "materials"

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Static(
            "TALISMANS · Ethereum Mainnet",
            id="title-bar",
        )

        yield TalismansHeroMetrics()

        with Horizontal(id="middle-row"):
            yield TalismansLeaderboard()
            with Vertical(id="right-col"):
                yield TalismansSparkline()
                yield TalismansSignals()

        yield Static("─" * 300, id="separator")

        with Horizontal(id="bottom-row"):
            yield TalismansActivityFeed()
            # Both tables live in the layout; one is hidden at a time.
            yield TalismansMatrixTable(id="tal-matrix-table")
            yield TalismansMaterialsTable(id="tal-materials-table")

        yield StatusBar()

    def on_mount(self) -> None:
        # Start with Matrix visible, Materials hidden.
        try:
            self.query_one("#tal-materials-table").display = False
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Actions / bindings
    # ------------------------------------------------------------------

    def action_toggle_view(self) -> None:
        if self._active_view == "matrix":
            self._active_view = "materials"
            try:
                self.query_one("#tal-matrix-table").display = False
                self.query_one("#tal-materials-table").display = True
            except Exception:
                pass
        else:
            self._active_view = "matrix"
            try:
                self.query_one("#tal-matrix-table").display = True
                self.query_one("#tal-materials-table").display = False
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
            self.query_one(StatusBar).set_game_name("talismans")
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

    async def _do_refresh(self) -> None:
        try:
            data = await self._data_manager.fetch_and_compute()
        except Exception as exc:
            logger.debug("Talismans refresh failed: %s", exc)
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
            live = data.get("live_tokens", 0) or 0
            mythic = data.get("mythic_count", 0) or 0
            cores = data.get("total_cores", 0) or 0
            self.query_one("#title-bar", Static).update(
                f"TALISMANS · {live} live · {mythic} mythic · cores {cores}"
            )
        except Exception as exc:
            logger.debug("Failed to update title bar: %s", exc)

        # Hero metrics
        try:
            self.query_one(TalismansHeroMetrics).update_data(
                live_tokens=data.get("live_tokens"),
                token_drift=data.get("token_drift"),
                mythic_count=data.get("mythic_count"),
                mythic_pct=data.get("mythic_pct"),
                mythics_ever_forged=data.get("mythics_ever_forged"),
                total_cores=data.get("total_cores"),
                cores_invariant_intact=data.get("cores_invariant_intact"),
                genesis_minted=data.get("genesis_minted"),
                operations_24h=data.get("operations_24h"),
                operations_total=data.get("operations_total"),
            )
        except Exception as exc:
            logger.debug("Failed to update TalismansHeroMetrics: %s", exc)

        # Leaderboard
        try:
            self.query_one(TalismansLeaderboard).update_data(
                top_collectors=data.get("top_collectors"),
            )
        except Exception as exc:
            logger.debug("Failed to update TalismansLeaderboard: %s", exc)

        # Sparkline
        try:
            self.query_one(TalismansSparkline).update_data(
                mythic_history=data.get("mythic_history"),
                operations_history=data.get("operations_history"),
            )
        except Exception as exc:
            logger.debug("Failed to update TalismansSparkline: %s", exc)

        # Signals
        try:
            self.query_one(TalismansSignals).update_data(
                conservation_signal=data.get("conservation_signal"),
                cutmerge_signal=data.get("cutmerge_signal"),
                forge_momentum_signal=data.get("forge_momentum_signal"),
                mythic_scarcity_signal=data.get("mythic_scarcity_signal"),
            )
        except Exception as exc:
            logger.debug("Failed to update TalismansSignals: %s", exc)

        # Activity feed
        try:
            self.query_one(TalismansActivityFeed).update_data(
                activity_events=data.get("activity_events"),
            )
        except Exception as exc:
            logger.debug("Failed to update TalismansActivityFeed: %s", exc)

        # Matrix table (bottom-right α)
        try:
            self.query_one(TalismansMatrixTable).update_data(
                essence_tier_matrix=data.get("essence_tier_matrix"),
            )
        except Exception as exc:
            logger.debug("Failed to update TalismansMatrixTable: %s", exc)

        # Materials table (bottom-right β)
        try:
            self.query_one(TalismansMaterialsTable).update_data(
                materials_ledger=data.get("materials_ledger"),
            )
        except Exception as exc:
            logger.debug("Failed to update TalismansMaterialsTable: %s", exc)

        # Status bar
        try:
            self.query_one(StatusBar).update_data(
                last_updated_seconds_ago=data.get("last_updated_seconds_ago", 0),
                error_count=data.get("error_count", 0),
                poll_interval=data.get("poll_interval", self._poll_interval),
            )
        except Exception as exc:
            logger.debug("Failed to update StatusBar: %s", exc)
