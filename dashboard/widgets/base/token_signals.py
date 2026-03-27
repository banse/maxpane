"""Token signals panel for the Base Terminal Token Detail view."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

# Signal label to color/indicator mapping
_SIGNAL_COLORS = {
    "bullish": ("[green]bullish[/]", "[green]\u25cf positive[/]"),
    "bearish": ("[red]bearish[/]", "[red]\u25cf negative[/]"),
    "normal": ("[dim]normal[/]", "[dim]\u25cf neutral[/]"),
    "high": ("[yellow]high[/]", "[yellow]\u25cf elevated[/]"),
    "low": ("[dim]low[/]", "[dim]\u25cf low[/]"),
    "healthy": ("[green]healthy[/]", "[green]\u25cf positive[/]"),
    "thin": ("[red]thin[/]", "[red]\u25cf warning[/]"),
    "neutral": ("[dim]neutral[/]", "[dim]\u25cf neutral[/]"),
}


def _format_signal(label: str) -> tuple[str, str]:
    """Return (value_markup, indicator_markup) for a signal label."""
    key = label.lower().strip() if label else "neutral"
    return _SIGNAL_COLORS.get(key, (f"[dim]{key}[/]", "[dim]\u25cf[/]"))


class TokenSignals(Vertical):
    """Static panel showing momentum, volume, liquidity signals."""

    DEFAULT_CSS = """
    TokenSignals > .ts-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    TokenSignals > .ts-body {
        width: 100%;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("SIGNALS", classes="ts-title")
        yield Static("[dim]  --[/]", id="ts-body", classes="ts-body")

    def update_data(self, signal: dict | None) -> None:
        """Update the signals display.

        Expected keys:
            momentum, volume, liquidity (each a string like 'bullish', 'normal', etc.).
        """
        body = self.query_one("#ts-body", Static)

        if not signal:
            body.update("[dim]  --[/]")
            return

        lines = []
        for key in ("momentum", "volume", "liquidity"):
            label = signal.get(key, "neutral")
            val_markup, indicator = _format_signal(label)
            display_key = f"{key.capitalize():<12}"
            lines.append(f"  {display_key} {val_markup:<16} {indicator}")

        body.update("\n".join(lines))
