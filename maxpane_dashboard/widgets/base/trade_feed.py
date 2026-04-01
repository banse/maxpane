"""Recent trades feed for the Base Terminal Token Detail view."""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static


def _format_time(timestamp: float | int | str | None) -> str:
    """Convert a unix timestamp to HH:MM display format."""
    if timestamp is None:
        return "??:??"
    try:
        ts = float(timestamp)
        t = time.localtime(ts)
        return f"{t.tm_hour:02d}:{t.tm_min:02d}"
    except (ValueError, OSError):
        return "??:??"


def _format_amount(amount: float | int | None) -> str:
    """Format a token amount compactly: 142K, 1.2M, etc."""
    if amount is None:
        return "--"
    try:
        val = float(amount)
    except (ValueError, TypeError):
        return str(amount)

    if val >= 1_000_000:
        return f"{val / 1_000_000:.0f}M"
    if val >= 1_000:
        return f"{val / 1_000:.0f}K"
    return f"{val:,.0f}"


class TradeFeed(Vertical):
    """RichLog showing recent buy/sell trades. Green for buys, red for sells."""

    DEFAULT_CSS = """
    TradeFeed > .tf-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    TradeFeed > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
        background: $background;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._seen_keys: set[str] = set()

    def compose(self) -> ComposeResult:
        yield Static("RECENT TRADES", classes="tf-title")
        yield RichLog(id="trade-log", wrap=True, highlight=True, markup=True)

    def update_data(self, trades: list[dict] | None) -> None:
        """Update trades display.

        Each trade dict expected keys:
            timestamp, type (buy/sell), amount, eth_amount, price, symbol.
        """
        log = self.query_one("#trade-log", RichLog)

        if not trades:
            if not self._seen_keys:
                log.write("[dim]  No trades yet[/]")
            return

        for trade in reversed(trades):
            ts = trade.get("timestamp")
            key = f"{ts}:{trade.get('type')}:{trade.get('amount')}:{trade.get('price')}"
            if key in self._seen_keys:
                continue
            self._seen_keys.add(key)

            time_str = _format_time(ts)
            trade_type = trade.get("type", "buy").lower()
            amount = _format_amount(trade.get("amount"))
            symbol = trade.get("symbol", "???")
            eth_amount = trade.get("eth_amount")
            price = trade.get("price")

            eth_str = f"{eth_amount:.2f} ETH" if eth_amount else "--"
            price_str = f"${price:.4f}" if price else "--"

            if trade_type == "buy":
                color = "green"
                label = "Buy "
            else:
                color = "red"
                label = "Sell"

            line = (
                f"  [dim]{time_str}[/]  [{color}]{label}[/]  "
                f"{amount:>8} {symbol:<8}  {eth_str:>10}  {price_str}"
            )
            log.write(line)

    def clear_trades(self) -> None:
        """Clear the trade log (used when switching tokens)."""
        self._seen_keys.clear()
        log = self.query_one("#trade-log", RichLog)
        log.clear()
