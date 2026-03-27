"""Token price hero box for the Base Terminal Token Detail view."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from dashboard.analytics.base_tokens import (
    format_change,
    format_market_cap,
    format_price,
)


class TokenPrice(Vertical):
    """Static panel showing token price, 24h change, mcap/fdv/liquidity."""

    DEFAULT_CSS = """
    TokenPrice > .tp-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    TokenPrice > .tp-body {
        width: 100%;
        padding: 0 1;
        border: solid $panel;
        background: $surface;
        height: auto;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("PRICE", classes="tp-title")
        yield Static(
            "[dim]  --[/]",
            id="tp-body",
            classes="tp-body",
        )

    def update_data(self, detail: dict | None) -> None:
        """Update the price display.

        Expected keys:
            price_usd, price_change_24h, market_cap, fdv, liquidity.
        """
        body = self.query_one("#tp-body", Static)

        if not detail:
            body.update("[dim]  --[/]")
            return

        price = detail.get("price_usd", 0)
        change_24h = detail.get("price_change_24h")
        mcap = detail.get("market_cap", 0)
        fdv = detail.get("fdv", 0)
        liq = detail.get("liquidity", 0)

        price_str = format_price(price)
        change_str = format_change(change_24h)

        # Arrow direction
        if change_24h is not None and change_24h > 0:
            arrow = "[green]\u25b2[/]"
        elif change_24h is not None and change_24h < 0:
            arrow = "[red]\u25bc[/]"
        else:
            arrow = " "

        mcap_str = format_market_cap(mcap) if mcap else "--"
        fdv_str = format_market_cap(fdv) if fdv else "--"
        liq_str = format_market_cap(liq) if liq else "--"

        lines = [
            f"  [bold]{price_str}[/]",
            f"  {arrow} {change_str} (24h)",
            f"  MCap: {mcap_str}  FDV: {fdv_str}",
            f"  Liq: {liq_str}",
        ]
        body.update("\n".join(lines))
