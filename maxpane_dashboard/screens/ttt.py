"""TTTScreen -- Ten Thousand Tokens dashboard as a Textual Screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from maxpane_dashboard.data.ttt_manager import TTTManager
from maxpane_dashboard.screens.dashboard_screen import DashboardScreen, keys
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


class TTTScreen(DashboardScreen):
    """Ten Thousand Tokens dashboard.

    Mirrors the layout pattern used by :class:`OCMScreen` but adds a
    Fees/Claims toggle (``c`` key) since the bottom-right slot serves two
    complementary tables.
    """

    #: Only the key this screen adds: Textual merges ``BINDINGS`` along the
    #: MRO, so ``r`` still refreshes through
    #: :class:`~maxpane_dashboard.screens.dashboard_screen.DashboardScreen`.
    BINDINGS = [
        Binding("c", "toggle_view", "Toggle Fees/Claims", show=True),
    ]

    #: The words the status bar shows for this dashboard.
    GAME_NAME = "ten thousand tokens"

    #: Worker name for the guarded refresh (see RefreshGuard).
    REFRESH_WORKER_NAME = "ttt-refresh"

    #: Transcribed from the seven hand-written dispatch blocks, default for
    #: default; the status bar is updated by the base.
    PANELS = (
        (
            TTTHeroMetrics,
            keys(
                "unburned",
                "burned_pct",
                "launches",
                "launches_24h",
                "holder_pool_eth_total",
                "holder_pool_eth_24h",
                "total_mcap_usd",
                "total_mcap_eth",
                "total_mcap_token_count",
            ),
        ),
        (TTTLeaderboard, keys("top_tokens_by_volume")),
        (TTTSparkline, keys("burns_history", "volume_history", volume_history=[])),
        (
            TTTSignals,
            keys(
                "fresh_launch_signal",
                "buybacks_ready_signal",
                "decay_window_signal",
                "concentration_signal",
            ),
        ),
        (TTTActivityFeed, keys("activity_events")),
        # Bottom-right alpha and gamma: both mounted, one displayed at a time,
        # so both are updated on every refresh and the toggle is free.
        (TTTFeesTable, keys("top_fee_engines")),
        (TTTClaimsTable, keys("claim_math_scenarios")),
    )

    def __init__(
        self,
        data_manager: TTTManager,
        poll_interval: int = 30,
        name: str = "ttt",
        **kwargs,
    ):
        super().__init__(data_manager, poll_interval, name=name, **kwargs)
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

    def _prime_status_bar(self, bar: StatusBar) -> None:
        """The one extra line this screen primes: which table owns the slot."""
        bar.set_active_view(self._active_view)

    def _update_title(self, data: dict) -> None:
        launches = data.get("launches", 0) or 0
        max_supply = data.get("max_supply", 10_000) or 10_000
        self.query_one("#title-bar", Static).update(
            f"Ten Thousand Tokens · Ethereum Mainnet · "
            f"{launches}/{max_supply:,}"
        )
