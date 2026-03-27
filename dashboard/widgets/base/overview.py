"""Bloomberg-style overview panel for Base Terminal (View 5).

Uses Textual layout containers for proper fullscreen rendering instead of
hardcoded text-art boxes.
"""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Static

from dashboard.analytics.base_tokens import (
    classify_token_status,
    format_change,
    format_market_cap,
    format_price,
    format_volume,
)
from dashboard.data.base_models import BaseToken, TokenLaunch, TrendingPool

# ---------------------------------------------------------------------------
# Sparkline rendering
# ---------------------------------------------------------------------------

_SPARK_CHARS = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
_SPARK_WIDTH = 35
_MAX_SPARKLINE_TOKENS = 10
_BAR_CHAR = "\u2588"
_MAX_BAR_WIDTH = 28
_MAX_VOLUME_TOKENS = 5
_MAX_MOVERS = 5
_MAX_LAUNCHES = 5
_MAX_POOLS = 5


def _build_sparkline(
    points: list[tuple[float, float]], width: int = _SPARK_WIDTH
) -> str:
    if len(points) < 2:
        return _SPARK_CHARS[0] * width
    values = [p[1] for p in points]
    if len(values) > width:
        values = values[-width:]
    lo, hi = min(values), max(values)
    span = hi - lo
    chars: list[str] = []
    for v in values:
        if span == 0:
            idx = 0
        else:
            idx = int((v - lo) / span * (len(_SPARK_CHARS) - 1))
            idx = max(0, min(len(_SPARK_CHARS) - 1, idx))
        chars.append(_SPARK_CHARS[idx])
    while len(chars) < width:
        chars.insert(0, _SPARK_CHARS[0])
    return "".join(chars)


def _format_age(timestamp: float | int | None) -> str:
    if timestamp is None:
        return "--"
    try:
        delta = int(time.time() - float(timestamp))
    except (ValueError, TypeError):
        return "--"
    if delta < 0:
        return "just now"
    if delta < 60:
        return f"{delta}s ago"
    minutes = delta // 60
    hours = minutes // 60
    if hours == 0:
        return f"{minutes}m ago"
    return f"{hours}h {minutes % 60}m ago"


def _status_dot(status: str) -> str:
    colour_map = {
        "pumping": "green",
        "recovering": "yellow",
        "stable": "dim",
        "dumping": "red",
        "crashed": "red bold",
    }
    colour = colour_map.get(status, "dim")
    return f"[{colour}]\u25cf {status}[/]"


# ---------------------------------------------------------------------------
# Hero card widgets
# ---------------------------------------------------------------------------


class _HeroCard(Static):
    """A single hero metric card with border."""

    DEFAULT_CSS = """
    _HeroCard {
        width: 1fr;
        height: 5;
        border: solid $panel;
        padding: 0 1;
        content-align: center middle;
    }
    """


class OverviewHero(Horizontal):
    """Top row of 4 equal-width hero metric cards."""

    DEFAULT_CSS = """
    OverviewHero {
        width: 100%;
        height: auto;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield _HeroCard("ETH\n[bold]...[/]", id="ov-h-eth")
        yield _HeroCard("TOKENS\n[bold]...[/]", id="ov-h-tokens")
        yield _HeroCard("LAUNCHES\n[bold]...[/]", id="ov-h-launches")
        yield _HeroCard("MARKET\n[bold]...[/]", id="ov-h-market")


# ---------------------------------------------------------------------------
# Main overview panel
# ---------------------------------------------------------------------------


class OverviewPanel(Vertical):
    """Bloomberg-style multi-chart overview combining all Base Terminal data."""

    DEFAULT_CSS = """
    OverviewPanel > .ov-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    OverviewPanel .ov-sub-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    OverviewPanel DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield OverviewHero(id="ov-hero-row")
        yield Static("", id="ov-sparklines", classes="ov-section")
        yield Static("\u2500" * 300, id="ov-sep")
        with Horizontal(id="ov-bottom"):
            with Vertical(id="ov-left"):
                yield Static("VOLUME RANKING", classes="ov-sub-title")
                yield DataTable(id="ov-vol-table")
                yield Static("RECENT LAUNCHES", classes="ov-sub-title")
                yield DataTable(id="ov-launch-table")
            with Vertical(id="ov-right"):
                yield Static("MOVERS", classes="ov-sub-title")
                yield DataTable(id="ov-movers-table")
                yield Static("TRENDING POOLS", classes="ov-sub-title")
                yield DataTable(id="ov-pools-table")

    def on_mount(self) -> None:
        # Volume ranking table
        vol_table = self.query_one("#ov-vol-table", DataTable)
        vol_table.cursor_type = "none"
        vol_table.zebra_stripes = True
        vol_table.add_column("Token", width=10)
        vol_table.add_column("Bar", width=30)
        vol_table.add_column("Volume", width=10)

        # Recent launches table
        launch_table = self.query_one("#ov-launch-table", DataTable)
        launch_table.cursor_type = "none"
        launch_table.zebra_stripes = True
        launch_table.add_column("Name", width=22)
        launch_table.add_column("Deployer", width=10)
        launch_table.add_column("Age", width=12)

        # Movers table
        movers_table = self.query_one("#ov-movers-table", DataTable)
        movers_table.cursor_type = "none"
        movers_table.zebra_stripes = True
        movers_table.add_column("Dir", width=3)
        movers_table.add_column("Token", width=12)
        movers_table.add_column("Change", width=10)
        movers_table.add_column("Status", width=14)

        # Trending pools table
        pools_table = self.query_one("#ov-pools-table", DataTable)
        pools_table.cursor_type = "none"
        pools_table.zebra_stripes = True
        pools_table.add_column("Pool", width=16)
        pools_table.add_column("Volume", width=10)
        pools_table.add_column("Change", width=10)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_data(self, data: dict) -> None:
        try:
            self._update_hero(data)
        except Exception:
            pass
        try:
            self._update_sparklines(data)
        except Exception:
            pass
        try:
            self._update_bottom(data)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Hero row
    # ------------------------------------------------------------------

    def _update_hero(self, data: dict) -> None:
        tokens: list[BaseToken] = data.get("trending_tokens", [])
        launch_stats: dict = data.get("launch_stats", {})

        tracked = len(tokens)
        bullish = sum(
            1 for t in tokens
            if t.price_change_24h is not None and t.price_change_24h > 0
        )
        rate = launch_stats.get("launch_rate_per_hour", 0)
        graduated = launch_stats.get("graduated_count", 0)
        total_vol = sum(t.volume_24h for t in tokens) if tokens else 0
        vol_str = format_volume(total_vol)

        updated_ago = data.get("last_updated_seconds_ago", 0)
        updated_str = f"updated {int(updated_ago)}s ago"

        try:
            self.query_one("#ov-h-eth", _HeroCard).update(
                f"[dim]ETH[/]\n[bold]...[/]\n[dim]{updated_str}[/]"
            )
        except Exception:
            pass
        try:
            self.query_one("#ov-h-tokens", _HeroCard).update(
                f"[dim]TOKENS[/]\n[bold]Tracked: {tracked}[/]\n[dim]Bullish: {bullish}[/]"
            )
        except Exception:
            pass
        try:
            self.query_one("#ov-h-launches", _HeroCard).update(
                f"[dim]LAUNCHES[/]\n[bold]Rate: {rate}/hr[/]\n[dim]Graduated: {graduated}[/]"
            )
        except Exception:
            pass
        try:
            self.query_one("#ov-h-market", _HeroCard).update(
                f"[dim]MARKET[/]\n[bold]Bullish: {bullish}/{tracked}[/]\n[dim]Vol: {vol_str}[/]"
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Sparklines
    # ------------------------------------------------------------------

    def _update_sparklines(self, data: dict) -> None:
        tokens: list[BaseToken] = data.get("trending_tokens", [])
        price_histories: dict = data.get("price_histories", {})
        display = tokens[:_MAX_SPARKLINE_TOKENS]

        lines = ["[bold dim]PRICE SPARKLINES (top 10)[/]", ""]

        for token in display:
            history = price_histories.get(token.address.lower(), [])
            sparkline = _build_sparkline(history)
            change_24h = token.price_change_24h
            change_str = format_change(change_24h)
            price_str = format_price(token.price_usd)
            mcap_str = format_market_cap(token.market_cap) + " mcap"
            symbol = token.symbol[:8].ljust(8)

            if change_24h is not None and change_24h > 0:
                spark_colour = "green"
            elif change_24h is not None and change_24h < 0:
                spark_colour = "red"
            else:
                spark_colour = "dim"

            line = (
                f"[bold]{symbol}[/]"
                f" {price_str:>12}  "
                f"[{spark_colour}]{sparkline}[/]  "
                f"{change_str:>8}  "
                f"[dim]{mcap_str}[/]"
            )
            lines.append(line)

        if not display:
            lines.append("  [dim]No tokens tracked yet[/]")

        self.query_one("#ov-sparklines", Static).update("\n".join(lines))

    # ------------------------------------------------------------------
    # Bottom
    # ------------------------------------------------------------------

    def _update_bottom(self, data: dict) -> None:
        self._update_bottom_left(data)
        self._update_bottom_right(data)

    def _update_bottom_left(self, data: dict) -> None:
        volume_leaders: list[BaseToken] = data.get("volume_leaders", [])
        launches: list[TokenLaunch] = data.get("launches", [])

        # -- Volume ranking table --
        vol_table = self.query_one("#ov-vol-table", DataTable)
        vol_table.clear()

        vol_display = volume_leaders[:_MAX_VOLUME_TOKENS]
        max_vol = vol_display[0].volume_24h if vol_display else 0

        if not vol_display:
            vol_table.add_row("[dim]No volume data[/]", "", "")
        else:
            for token in vol_display:
                vol = token.volume_24h
                vol_str = format_volume(vol)
                symbol = token.symbol[:8]
                bar_len = max(1, int(vol / max_vol * _MAX_BAR_WIDTH)) if max_vol > 0 else 1
                bar = f"[cyan]{_BAR_CHAR * bar_len}[/]"
                vol_table.add_row(
                    f"[dim]{symbol}[/]",
                    bar,
                    f"[bold]{vol_str}[/]",
                )

        # -- Recent launches table --
        launch_table = self.query_one("#ov-launch-table", DataTable)
        launch_table.clear()

        launch_display = launches[:_MAX_LAUNCHES]

        if not launch_display:
            launch_table.add_row("[dim]No recent launches[/]", "", "")
        else:
            for launch in launch_display:
                age = _format_age(launch.created_at)
                launch_table.add_row(
                    launch.name[:20],
                    launch.deployer,
                    age,
                )

    def _update_bottom_right(self, data: dict) -> None:
        top_gainers: list[BaseToken] = data.get("top_gainers", [])
        top_losers: list[BaseToken] = data.get("top_losers", [])
        trending_pools: list[TrendingPool] = data.get("trending_pools", [])

        # -- Movers table --
        movers_table = self.query_one("#ov-movers-table", DataTable)
        movers_table.clear()

        has_movers = False

        for token in top_gainers[:_MAX_MOVERS]:
            change = token.price_change_24h
            pct = f"+{change:.1f}%" if change is not None else "+?%"
            symbol = token.symbol[:10]
            status = classify_token_status(token)
            dot = _status_dot(status)
            movers_table.add_row(
                "[green]\u25b2[/]",
                f"[bold]{symbol}[/]",
                pct,
                dot,
            )
            has_movers = True

        for token in top_losers[:_MAX_MOVERS]:
            change = token.price_change_24h
            pct = f"{change:.1f}%" if change is not None else "-?%"
            symbol = token.symbol[:10]
            status = classify_token_status(token)
            dot = _status_dot(status)
            movers_table.add_row(
                "[red]\u25bc[/]",
                f"[bold]{symbol}[/]",
                pct,
                dot,
            )
            has_movers = True

        if not has_movers:
            movers_table.add_row("--", "No movers", "--", "--")

        # -- Trending pools table --
        pools_table = self.query_one("#ov-pools-table", DataTable)
        pools_table.clear()

        pool_display = trending_pools[:_MAX_POOLS]

        if not pool_display:
            pools_table.add_row("[dim]No pools[/]", "--", "--")
        else:
            for pool in pool_display:
                pair = f"{pool.token_symbol}/WETH"
                pair_str = pair[:14]
                vol_str = format_volume(pool.volume_24h)
                change_str = format_change(pool.price_change_24h)
                pools_table.add_row(
                    f"[bold]{pair_str}[/]",
                    vol_str,
                    change_str,
                )
