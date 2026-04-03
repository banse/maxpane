"""Signals panel template -- copy and adapt for new game dashboards.

Pattern: Vertical container with individual Static widgets per signal
row.  Each row shows a label, value, and colored indicator dot.
A recommendation line appears at the bottom.

Reference implementations:
  - maxpane_dashboard/widgets/frenpet/overview/fp_game_signals.py
  - maxpane_dashboard/widgets/cattown/ct_signals.py
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


def _fmt_signal(sig: dict) -> str:
    """Format a signal row: label, value, colored indicator.

    Expected keys: label, value_str, color, indicator (optional).
    """
    label = sig.get("label", "")
    value = sig.get("value_str", "")
    color = sig.get("color", "dim")
    indicator = sig.get("indicator", "\u25cf")
    return f"  [{color}]{indicator}[/] [dim]{label:<15}[/] [{color}]{value}[/]"


def _fmt_row(label: str, value: str, indicator: str = "", ind_color: str = "dim") -> str:
    """Format a signal row with fixed-width columns.

    Alternative to dict-based _fmt_signal for inline usage.
    """
    if indicator:
        return (
            f"  [dim]{label:<20}[/]"
            f"[bold white]{value:>12}[/]"
            f"  [{ind_color}]\u25cf {indicator:<10}[/]"
        )
    return (
        f"  [dim]{label:<20}[/]"
        f"[bold white]{value:>12}[/]"
    )


class GameSignals(Vertical):
    """Panel displaying analytical signals and recommendation.

    Rename for your game, e.g. ``CTSignals``, ``DOTASignals``.
    Adjust compose() signal IDs and update_data() parameters.
    """

    DEFAULT_CSS = """
    GameSignals > .signals-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    GameSignals > .signals-body {
        padding: 0 1;
        width: 100%;
    }
    GameSignals > .signals-rec {
        padding: 0 1;
        width: 100%;
        text-align: center;
        content-align: center middle;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("SIGNALS", classes="signals-title")
        yield Static("", id="game-sig-spacer")
        yield Static("[dim]  Loading...[/]", classes="signals-body", id="game-sig-line-0")
        yield Static("", classes="signals-body", id="game-sig-line-1")
        yield Static("", classes="signals-body", id="game-sig-line-2")
        yield Static("", id="game-sig-spacer-2")
        yield Static("", classes="signals-rec", id="game-sig-recommendation")

    def update_data(
        self,
        signal_0: dict | None = None,
        signal_1: dict | None = None,
        signal_2: dict | None = None,
        recommendation: str = "",
        **_kwargs,
    ) -> None:
        """Update signal lines and recommendation.

        Each signal dict should contain: label, value_str, color.
        Adapt the number of signals and their meaning to your game.
        """
        # Signal 0
        w = self.query_one("#game-sig-line-0", Static)
        if signal_0:
            w.update(_fmt_signal(signal_0))
        else:
            w.update(_fmt_signal({"label": "Signal 1", "value_str": "--", "color": "dim"}))

        # Signal 1
        w = self.query_one("#game-sig-line-1", Static)
        if signal_1:
            w.update(_fmt_signal(signal_1))
        else:
            w.update(_fmt_signal({"label": "Signal 2", "value_str": "--", "color": "dim"}))

        # Signal 2
        w = self.query_one("#game-sig-line-2", Static)
        if signal_2:
            w.update(_fmt_signal(signal_2))
        else:
            w.update(_fmt_signal({"label": "Signal 3", "value_str": "--", "color": "dim"}))

        # Recommendation
        w = self.query_one("#game-sig-recommendation", Static)
        if recommendation:
            w.update(f"  [dim]\u2192 Recommendation:[/] [bold]{recommendation}[/]")
        else:
            w.update("")
