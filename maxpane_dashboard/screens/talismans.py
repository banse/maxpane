"""TalismansScreen -- Talismans NFT dashboard as a Textual Screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import Static
from textual.containers import Horizontal, Vertical

from maxpane_dashboard.data.talismans_manager import TalismansManager
from maxpane_dashboard.screens.dashboard_screen import DashboardScreen, keys
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


class TalismansScreen(DashboardScreen):
    """Talismans core-conservation NFT dashboard.

    Mirrors the layout pattern used by :class:`TTTScreen` but adds a
    Matrix/Materials toggle (``c`` key) since the bottom-right slot serves
    two complementary tables.
    """

    #: Only the key this screen adds: Textual merges ``BINDINGS`` along the
    #: MRO, so ``r`` still refreshes through
    #: :class:`~maxpane_dashboard.screens.dashboard_screen.DashboardScreen`.
    BINDINGS = [
        Binding("c", "toggle_view", "Matrix/Materials", show=True),
    ]

    #: The words the status bar shows for this dashboard.
    GAME_NAME = "talismans"

    #: Worker name for the guarded refresh (see RefreshGuard).
    REFRESH_WORKER_NAME = "talismans-refresh"

    #: Transcribed from the seven hand-written dispatch blocks, default for
    #: default; the status bar is updated by the base.
    PANELS = (
        (
            TalismansHeroMetrics,
            keys(
                "live_tokens",
                "token_drift",
                "mythic_count",
                "mythic_pct",
                "mythics_ever_forged",
                "total_cores",
                "cores_invariant_intact",
                "genesis_minted",
                "operations_24h",
                "operations_total",
            ),
        ),
        (TalismansLeaderboard, keys("top_collectors")),
        (TalismansSparkline, keys("mythic_history", "operations_history")),
        (
            TalismansSignals,
            keys(
                "conservation_signal",
                "cutmerge_signal",
                "forge_momentum_signal",
                "mythic_scarcity_signal",
            ),
        ),
        (TalismansActivityFeed, keys("activity_events")),
        # Bottom-right alpha and beta: both mounted, one displayed at a time,
        # so both are updated on every refresh and the toggle is free.
        (TalismansMatrixTable, keys("essence_tier_matrix")),
        (TalismansMaterialsTable, keys("materials_ledger")),
    )

    def __init__(
        self,
        data_manager: TalismansManager,
        poll_interval: int = 30,
        name: str = "talismans",
        **kwargs,
    ):
        super().__init__(data_manager, poll_interval, name=name, **kwargs)
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

    def _prime_status_bar(self, bar: StatusBar) -> None:
        """The one extra line this screen primes: which table owns the slot."""
        bar.set_active_view(self._active_view)

    def _update_title(self, data: dict) -> None:
        live = data.get("live_tokens", 0) or 0
        mythic = data.get("mythic_count", 0) or 0
        # `total_cores` is None while enumeration is still syncing (LOW-12):
        # an unfinished count is a failed read, and a failed read renders as
        # "--", never as 0. Coercing it to 0 here showed "cores 0" on a cold
        # start, which reads as a real -- and alarming -- measurement.
        raw_cores = data.get("total_cores")
        cores = "--" if raw_cores is None else f"{raw_cores}"
        self.query_one("#title-bar", Static).update(
            f"TALISMANS · {live} live · {mythic} mythic · cores {cores}"
        )
