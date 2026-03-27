"""BaseTerminalScreen -- Base chain terminal dashboard with 5 views."""

from __future__ import annotations

import logging

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import ContentSwitcher, Static

from dashboard.widgets.base import (
    FeeClaims,
    FeeLeaderboard,
    FeeStats,
    GeckoPools,
    GraduatedTokens,
    LaunchFeed,
    LaunchStats,
    OverviewPanel,
    PoolInfo,
    PriceSparklines,
    TokenChart,
    TokenPrice,
    TokenSignals,
    TopMovers,
    TradeFeed,
    VolumeSparklines,
    TrendingTable,
    VolumeBars,
)
from dashboard.widgets.status_bar import StatusBar

logger = logging.getLogger(__name__)


def _short_addr(address: str | None) -> str:
    """Shorten 0x... address for display."""
    if not address:
        return ""
    if len(address) > 10:
        return f"{address[:6]}...{address[-4:]}"
    return address


class BaseTerminalScreen(Screen):
    """Base chain terminal dashboard with 5 views."""

    BINDINGS = [
        Binding("1", "show_trending", "Trending", show=False),
        Binding("2", "show_launches", "Launches", show=False),
        Binding("3", "show_token", "Token", show=False),
        Binding("4", "show_fees", "Fees", show=False),
        Binding("5", "show_overview", "Overview", show=False),
        Binding("r", "refresh", "Refresh", show=False),
    ]

    def __init__(
        self,
        manager,
        poll_interval: int = 30,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._manager = manager
        self._poll_interval = poll_interval
        self._refresh_timer = None
        self._selected_token: str | None = None
        self._current_view: str = "trending"

    def compose(self) -> ComposeResult:
        yield Static(
            "BASE TERMINAL \u00b7 $ETH ... \u00b7 Gas ... \u00b7 Block ...",
            id="bt-title",
        )

        # View selector indicator
        yield Static(
            "[bold reverse] 1 Trending [/]  [dim][2] Launches[/]  "
            "[dim][3] Token[/]  [dim][4] Fees[/]  [dim][5] Overview[/]",
            id="bt-view-selector",
        )

        with ContentSwitcher(initial="trending"):
            # -- Trending View (3 rows) --
            with Vertical(id="trending"):
                # Row 1: Top movers (left) | Price sparklines (right)
                with Horizontal(id="bt-trending-top"):
                    yield TopMovers(id="bt-top-movers")
                    yield PriceSparklines(id="bt-sparklines")

                yield Static("\u2500" * 300, id="bt-trending-sep1")

                # Row 2: Trending tokens table (full width)
                yield TrendingTable(id="bt-trending-table")

                yield Static("\u2500" * 300, id="bt-trending-sep2")

                # Row 3: Trending pools (left) | Volume sparklines (right)
                with Horizontal(id="bt-trending-bottom"):
                    yield GeckoPools(id="bt-gecko-pools")
                    yield VolumeSparklines(id="bt-volspark")

            # -- Launches View --
            with Vertical(id="launches"):
                with Horizontal(id="bt-launch-row"):
                    yield LaunchFeed(id="bt-launch-feed")
                    with Vertical(id="bt-launch-right"):
                        yield LaunchStats(id="bt-launch-stats")
                        yield GraduatedTokens(id="bt-graduated")

            # -- Token Detail View --
            with Vertical(id="token"):
                yield Static(
                    "[dim]Select a token from Trending or Launches[/]",
                    id="bt-token-header",
                )

                # Top row: price box + sparkline chart
                with Horizontal(id="bt-token-top"):
                    yield TokenPrice(id="bt-token-price")
                    yield TokenChart(id="bt-token-chart")

                yield Static(
                    "\u2500" * 300,
                    id="bt-token-sep",
                )

                # Bottom row: pool + signals | trades
                with Horizontal(id="bt-token-bottom"):
                    with Vertical(id="bt-token-left"):
                        yield PoolInfo(id="bt-pool-info")
                        yield TokenSignals(id="bt-token-signals")
                    yield TradeFeed(id="bt-trade-feed")

            # -- Fee Monitor View --
            with Vertical(id="fees"):
                yield Static(
                    "[dim]FEE MONITOR \u00b7 Clanker LP Locker[/]",
                    id="bt-fee-header",
                )

                # Top row: claims feed | leaderboard
                with Horizontal(id="bt-fee-top"):
                    yield FeeClaims(id="bt-fee-claims")
                    yield FeeLeaderboard(id="bt-fee-leaderboard")

                yield Static(
                    "\u2500" * 300,
                    id="bt-fee-sep",
                )

                # Bottom row: stats | alerts placeholder
                with Horizontal(id="bt-fee-bottom"):
                    yield FeeStats(id="bt-fee-stats")
                    with Vertical(id="bt-fee-alerts"):
                        yield Static("ALERTS", id="bt-fee-alerts-title")
                        yield Static(
                            "[dim]  No alerts[/]",
                            id="bt-fee-alerts-body",
                        )

            # -- Overview View (Phase 5) --
            with Vertical(id="overview"):
                yield OverviewPanel(id="bt-overview")

        # Status bar
        yield StatusBar()

    def on_screen_resume(self) -> None:
        """Start polling when this screen is active."""
        self._do_initial_refresh()
        self._refresh_timer = self.set_interval(
            self._poll_interval, self._schedule_refresh
        )
        # Update status bar with current theme name
        try:
            self.query_one(StatusBar).set_theme_name(self.app.theme)
            self.query_one(StatusBar).set_game_name("base terminal")
        except Exception:
            pass

    def on_screen_suspend(self) -> None:
        """Stop polling when switching away."""
        if self._refresh_timer:
            self._refresh_timer.stop()
            self._refresh_timer = None

    def _do_initial_refresh(self) -> None:
        """Trigger an immediate refresh when the screen appears."""
        self.run_worker(self._do_refresh(), exclusive=True, name="base-refresh")

    def _schedule_refresh(self) -> None:
        """Schedule a refresh via a worker so it runs async."""
        self.run_worker(self._do_refresh(), exclusive=True, name="base-refresh")

    async def _do_refresh(self) -> None:
        """Fetch data and update widgets."""
        try:
            data = await self._manager.fetch_and_compute()
        except Exception as exc:
            logger.error("Base Terminal refresh failed: %s", exc)
            try:
                self.query_one(StatusBar).update_data(
                    last_updated_seconds_ago=999,
                    error_count=0,
                    poll_interval=self._poll_interval,
                )
            except Exception:
                pass
            return

        # Update title bar with live data when available
        eth_price = data.get("eth_price", "...")
        gas_price = data.get("gas_price", "...")
        block_number = data.get("block_number", "...")
        try:
            title = self.query_one("#bt-title", Static)
            title.update(
                f"BASE TERMINAL \u00b7 $ETH {eth_price}"
                f" \u00b7 Gas {gas_price}"
                f" \u00b7 Block {block_number}"
            )
        except Exception:
            pass

        # -- Update trending widgets --
        trending_tokens = data.get("trending_tokens", [])
        trending_pools = data.get("trending_pools", [])
        top_gainers = data.get("top_gainers", [])
        top_losers = data.get("top_losers", [])
        price_histories = data.get("price_histories", {})

        try:
            self.query_one("#bt-trending-table", TrendingTable).update_data(
                trending_tokens
            )
        except Exception as exc:
            logger.warning("Failed to update TrendingTable: %s", exc)

        try:
            self.query_one("#bt-sparklines", PriceSparklines).update_data(
                trending_tokens, price_histories
            )
        except Exception as exc:
            logger.warning("Failed to update PriceSparklines: %s", exc)

        try:
            self.query_one("#bt-top-movers", TopMovers).update_data(
                top_gainers, top_losers
            )
        except Exception as exc:
            logger.warning("Failed to update TopMovers: %s", exc)

        try:
            self.query_one("#bt-gecko-pools", GeckoPools).update_data(
                trending_pools
            )
        except Exception as exc:
            logger.warning("Failed to update GeckoPools: %s", exc)

        try:
            self.query_one("#bt-volspark", VolumeSparklines).update_data(
                trending_tokens, price_histories
            )
        except Exception as exc:
            logger.warning("Failed to update VolumeSparklines: %s", exc)

        # -- Update launch radar widgets --
        launches = data.get("launches", [])
        launch_stats = data.get("launch_stats", {})
        graduated = data.get("graduated_launches", [])

        try:
            self.query_one("#bt-launch-feed", LaunchFeed).update_data(launches)
        except Exception as exc:
            logger.warning("Failed to update LaunchFeed: %s", exc)

        try:
            self.query_one("#bt-launch-stats", LaunchStats).update_data(launch_stats)
        except Exception as exc:
            logger.warning("Failed to update LaunchStats: %s", exc)

        try:
            self.query_one("#bt-graduated", GraduatedTokens).update_data(graduated)
        except Exception as exc:
            logger.warning("Failed to update GraduatedTokens: %s", exc)

        # -- Update overview panel --
        try:
            self.query_one("#bt-overview", OverviewPanel).update_data(data)
        except Exception as exc:
            logger.warning("Failed to update OverviewPanel: %s", exc)

        # -- Update token detail if on token view with a selection --
        if self._current_view == "token" and self._selected_token:
            await self._refresh_token_detail()

        # Update status bar
        try:
            self.query_one(StatusBar).update_data(
                last_updated_seconds_ago=data.get("last_updated_seconds_ago", 0),
                error_count=data.get("error_count", 0),
                poll_interval=data.get("poll_interval", self._poll_interval),
            )
        except Exception as exc:
            logger.warning("Failed to update StatusBar: %s", exc)

    async def _refresh_token_detail(self) -> None:
        """Fetch and update the Token Detail view widgets."""
        if not self._selected_token:
            return

        try:
            detail = await self._manager.fetch_selected_token(self._selected_token)
        except Exception as exc:
            logger.warning("Failed to fetch token detail: %s", exc)
            return

        if not detail:
            return

        # Update header
        symbol = detail.get("symbol", "???")
        address = detail.get("address", "")
        addr_short = _short_addr(address)
        header_text = (
            f"TOKEN: ${symbol} \u00b7 {addr_short}"
            "                                    "
            "[dim][enter on trending to select][/]"
        )
        try:
            self.query_one("#bt-token-header", Static).update(header_text)
        except Exception:
            pass

        # Update price hero
        try:
            self.query_one("#bt-token-price", TokenPrice).update_data(detail)
        except Exception as exc:
            logger.warning("Failed to update TokenPrice: %s", exc)

        # Update sparkline chart
        price_history = detail.get("price_history")
        try:
            self.query_one("#bt-token-chart", TokenChart).update_data(price_history)
        except Exception as exc:
            logger.warning("Failed to update TokenChart: %s", exc)

        # Update pool info
        try:
            self.query_one("#bt-pool-info", PoolInfo).update_data(detail)
        except Exception as exc:
            logger.warning("Failed to update PoolInfo: %s", exc)

        # Update trade feed
        trades = detail.get("trades", [])
        try:
            self.query_one("#bt-trade-feed", TradeFeed).update_data(trades)
        except Exception as exc:
            logger.warning("Failed to update TradeFeed: %s", exc)

        # Update signals
        signals = detail.get("signals")
        try:
            self.query_one("#bt-token-signals", TokenSignals).update_data(signals)
        except Exception as exc:
            logger.warning("Failed to update TokenSignals: %s", exc)

    def select_token(self, token_id: str) -> None:
        """Set the selected token and switch to token detail view.

        Called externally (e.g. from TrendingTable row selection).
        """
        self._selected_token = token_id

        # Clear trade feed for new token
        try:
            self.query_one("#bt-trade-feed", TradeFeed).clear_trades()
        except Exception:
            pass

        # Switch to token view
        self.action_show_token()

        # Trigger immediate refresh for the token detail
        self.run_worker(
            self._refresh_token_detail(), exclusive=False, name="token-detail"
        )

    def action_refresh(self) -> None:
        """Immediate refresh triggered by the 'r' keybinding."""
        self.run_worker(self._do_refresh(), exclusive=True, name="base-refresh")

    # ------------------------------------------------------------------
    # View switching
    # ------------------------------------------------------------------

    def action_show_trending(self) -> None:
        self.query_one(ContentSwitcher).current = "trending"
        self._current_view = "trending"
        self._update_selector(1)

    def action_show_launches(self) -> None:
        self.query_one(ContentSwitcher).current = "launches"
        self._current_view = "launches"
        self._update_selector(2)

    def action_show_token(self) -> None:
        self.query_one(ContentSwitcher).current = "token"
        self._current_view = "token"
        self._update_selector(3)

    def action_show_fees(self) -> None:
        self.query_one(ContentSwitcher).current = "fees"
        self._current_view = "fees"
        self._update_selector(4)

    def action_show_overview(self) -> None:
        self.query_one(ContentSwitcher).current = "overview"
        self._current_view = "overview"
        self._update_selector(5)

    def _update_selector(self, active: int) -> None:
        labels = ["Trending", "Launches", "Token", "Fees", "Overview"]
        parts = []
        for i, label in enumerate(labels, 1):
            if i == active:
                parts.append(f"[bold reverse] {i} {label} [/]")
            else:
                parts.append(f"[dim][{i}] {label}[/]")
        self.query_one("#bt-view-selector", Static).update("  ".join(parts))
