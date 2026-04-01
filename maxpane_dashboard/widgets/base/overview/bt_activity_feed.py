"""Volume activity feed for the Base Trading Overview view."""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static


def _format_volume(value: float) -> str:
    """Format a dollar volume with K/M/B suffix."""
    try:
        v = float(value)
        if v >= 1_000_000:
            return f"${v / 1_000_000:.1f}M"
        elif v >= 1_000:
            return f"${v / 1_000:.1f}K"
        return f"${v:,.0f}"
    except (ValueError, TypeError):
        return "$?"


def _strip_non_ascii(text: str) -> str:
    """Remove non-ASCII for alignment."""
    return "".join(ch for ch in text if ord(ch) < 128).strip()


def _format_count(value: int) -> str:
    """Format a trade count with K suffix."""
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def _token_to_markup(token: dict) -> str:
    """Convert a token volume entry into a Rich-markup formatted line."""
    symbol = _strip_non_ascii(token.get("symbol", "???"))[:8]
    vol = _format_volume(token.get("volume_24h", 0))
    liq = _format_volume(token.get("liquidity", 0))
    buys = token.get("buys_24h", 0)
    sells = token.get("sells_24h", 0)
    change = token.get("price_change_24h", 0) or 0

    # Buy/sell pressure indicator
    if buys + sells > 0:
        ratio = buys / (buys + sells)
        if ratio > 0.55:
            pressure = "[green]BUY [/]"
        elif ratio < 0.45:
            pressure = "[red]SELL[/]"
        else:
            pressure = "[yellow]EVEN[/]"
    else:
        pressure = "[dim] -- [/]"

    # Price change color
    if change > 0:
        change_str = f"[green]{'+' + f'{change:.1f}':>6}%[/]"
    elif change < 0:
        change_str = f"[red]{f'{change:.1f}':>6}%[/]"
    else:
        change_str = f"[dim]{'0.0':>6}%[/]"

    # Buy/sell counts
    bs_str = f"{_format_count(buys)}/{_format_count(sells)}"

    return (
        f"  {pressure}  "
        f"[cyan]{symbol:<8}[/]  "
        f"{vol:>8}  "
        f"{change_str}  "
        f"[dim]{liq:>8}[/]  "
        f"[dim]{bs_str:>11}[/]"
    )


class BTActivityFeed(Vertical):
    """Activity feed showing trending tokens with volume and buy/sell pressure."""

    DEFAULT_CSS = """
    BTActivityFeed > .bto-feed-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    BTActivityFeed > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._has_data = False

    def compose(self) -> ComposeResult:
        yield Static("ACTIVITY", classes="bto-feed-title")
        yield RichLog(id="bto-activity-log", wrap=True, highlight=True, markup=True)

    def update_data(self, whale_trades: list[dict] | None = None) -> None:
        """Show tokens ranked by volume with buy/sell pressure."""
        log = self.query_one("#bto-activity-log", RichLog)
        tokens = whale_trades or []

        if not tokens:
            if not self._has_data:
                log.write("[dim]  No activity yet[/]")
            return

        self._has_data = True
        log.clear()
        log.auto_scroll = False

        # Header
        log.write(
            f"  [dim]{'':4}  {'Token':<8}  {'Volume':>8}  {'Change':>7}  {'Liq':>8}  {'Buys/Sells':>11}[/]"
        )

        for token in tokens:
            log.write(_token_to_markup(token))

        self.call_after_refresh(log.scroll_home, animate=False)
