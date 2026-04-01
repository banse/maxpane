"""Signals panel for Cat Town dashboard."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


class CTSignals(Vertical):
    """Panel displaying Cat Town analytical signals and recommendation."""

    DEFAULT_CSS = """
    CTSignals > .signals-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    CTSignals > .signals-body {
        padding: 0 1;
        width: 100%;
    }
    CTSignals > .signals-rec {
        padding: 0 1;
        width: 100%;
        text-align: center;
        content-align: center middle;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("SIGNALS", classes="signals-title")
        yield Static("", id="ct-sig-spacer")
        yield Static("[dim]  Loading...[/]", classes="signals-body", id="ct-sig-conditions")
        yield Static("", classes="signals-body", id="ct-sig-legendary")
        yield Static("", classes="signals-body", id="ct-sig-cutoff")
        yield Static("", id="ct-sig-spacer-2")
        yield Static("", classes="signals-rec", id="ct-sig-recommendation")

    def update_data(
        self,
        condition_signal: dict | None = None,
        legendary_signal: dict | None = None,
        cutoff_signal: dict | None = None,
        recommendation: str = "",
        **_kwargs,
    ) -> None:
        """Update signal lines and recommendation."""
        # Conditions
        w = self.query_one("#ct-sig-conditions", Static)
        if condition_signal:
            w.update(_fmt(condition_signal))
        else:
            w.update(_fmt({"label": "Conditions", "value_str": "--", "color": "dim"}))

        # Legendary
        w = self.query_one("#ct-sig-legendary", Static)
        if legendary_signal:
            w.update(_fmt(legendary_signal))
        else:
            w.update(_fmt({"label": "Legendary", "value_str": "--", "color": "dim"}))

        # Top 10 Cutoff
        w = self.query_one("#ct-sig-cutoff", Static)
        if cutoff_signal:
            w.update(_fmt(cutoff_signal))
        else:
            w.update(_fmt({"label": "Top 10 Cutoff", "value_str": "--", "color": "dim"}))

        # Recommendation
        w = self.query_one("#ct-sig-recommendation", Static)
        if recommendation:
            w.update(f"  [dim]\u2192 Recommendation:[/] [bold]{recommendation}[/]")
        else:
            w.update("")


def _fmt(sig: dict) -> str:
    """Format a signal row: label, value, colored indicator."""
    label = sig.get("label", "")
    value = sig.get("value_str", "")
    color = sig.get("color", "dim")
    indicator = sig.get("indicator", "\u25cf")
    return f"  [{color}]{indicator}[/] [dim]{label:<15}[/] [{color}]{value}[/]"
