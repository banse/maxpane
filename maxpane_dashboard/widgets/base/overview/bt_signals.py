"""Trading signals panel for the Base Trading Overview view."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


def _signal_indicator(label: str, value: str | None) -> tuple[str, str]:
    """Return (display_value, color) for a signal."""
    if value is None:
        return "...", "dim"
    val_lower = str(value).lower()
    if val_lower in ("bullish", "strong_buy", "buy", "high", "rising"):
        return str(value), "green"
    elif val_lower in ("bearish", "strong_sell", "sell", "low", "falling"):
        return str(value), "red"
    elif val_lower in ("neutral", "hold", "normal", "flat", "moderate"):
        return str(value), "yellow"
    return str(value), "white"


class BTSignals(Vertical):
    """Panel displaying Base Trading analytical signals and recommendation."""

    DEFAULT_CSS = """
    BTSignals > .bto-sig-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    BTSignals > .bto-sig-body {
        padding: 0 1;
        width: 100%;
    }
    BTSignals > .bto-sig-rec {
        padding: 0 1;
        width: 100%;
        text-align: center;
        content-align: center middle;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("SIGNALS", classes="bto-sig-title")
        yield Static("", id="bto-sig-spacer")
        yield Static("[dim]  Loading...[/]", classes="bto-sig-body", id="bto-sig-buy-sell")
        yield Static("", classes="bto-sig-body", id="bto-sig-volume")
        yield Static("", classes="bto-sig-body", id="bto-sig-whale")
        yield Static("", id="bto-sig-spacer-2")
        yield Static("", classes="bto-sig-rec", id="bto-sig-recommendation")

    def update_data(
        self,
        buy_sell_signal: str | None = None,
        volume_signal: str | None = None,
        whale_signal: str | None = None,
        recommendation: str = "",
    ) -> None:
        """Update all signal lines with computed analytics."""
        # Buy/Sell Signal
        bs_display, bs_color = _signal_indicator("Buy/Sell", buy_sell_signal)
        self.query_one("#bto-sig-buy-sell", Static).update(
            f"  [dim]{'Buy/Sell':<20}[/]"
            f"[bold white]{bs_display:>12}[/]"
            f"  [{bs_color}]\u25cf[/]"
        )

        # Volume Signal
        vs_display, vs_color = _signal_indicator("Volume", volume_signal)
        self.query_one("#bto-sig-volume", Static).update(
            f"  [dim]{'Volume':<20}[/]"
            f"[bold white]{vs_display:>12}[/]"
            f"  [{vs_color}]\u25cf[/]"
        )

        # Whale Signal
        ws_display, ws_color = _signal_indicator("Whale", whale_signal)
        self.query_one("#bto-sig-whale", Static).update(
            f"  [dim]{'Whale Activity':<20}[/]"
            f"[bold white]{ws_display:>12}[/]"
            f"  [{ws_color}]\u25cf[/]"
        )

        # Recommendation
        if recommendation:
            self.query_one("#bto-sig-recommendation", Static).update(
                f"  [dim]\u2192 Recommendation:[/] [bold]{recommendation}[/]"
            )
        else:
            self.query_one("#bto-sig-recommendation", Static).update("")
