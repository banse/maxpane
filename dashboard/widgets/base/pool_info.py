"""Pool information panel for the Base Terminal Token Detail view."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


class PoolInfo(Vertical):
    """Static panel showing pool details: pair, DEX, fee tier, buy/sell counts."""

    DEFAULT_CSS = """
    PoolInfo > .pi-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    PoolInfo > .pi-body {
        width: 100%;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("POOL INFO", classes="pi-title")
        yield Static("[dim]  --[/]", id="pi-body", classes="pi-body")

    def update_data(self, detail: dict | None) -> None:
        """Update pool info display.

        Expected keys:
            pair_name, dex, fee_tier, buys_24h, sells_24h, buys_1h, sells_1h.
        """
        body = self.query_one("#pi-body", Static)

        if not detail:
            body.update("[dim]  --[/]")
            return

        pair = detail.get("pair_name", "--")
        dex = detail.get("dex", "--")
        fee = detail.get("fee_tier", "--")
        buys_24h = detail.get("buys_24h", 0)
        sells_24h = detail.get("sells_24h", 0)
        buys_1h = detail.get("buys_1h", 0)
        sells_1h = detail.get("sells_1h", 0)

        # Format counts with commas
        def _fmt(n: int | float) -> str:
            try:
                return f"{int(n):,}"
            except (ValueError, TypeError):
                return str(n)

        lines = [
            f"  Pair: [bold]{pair}[/] ({dex})",
            f"  Fee:  {fee}",
            f"  24h Buys: [green]{_fmt(buys_24h)}[/]  Sells: [red]{_fmt(sells_24h)}[/]",
            f"  1h  Buys: [green]{_fmt(buys_1h)}[/]   Sells: [red]{_fmt(sells_1h)}[/]",
        ]
        body.update("\n".join(lines))
