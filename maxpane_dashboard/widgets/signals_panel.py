"""Signals panel showing key game metrics and recommendations."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


def _ev_color(value: float) -> str:
    if value > 0:
        return "green"
    elif value < 0:
        return "red"
    return "white"


def _gap_trend_label(gap_rate: float) -> tuple[str, str]:
    """Return (label, color) for gap trend."""
    if gap_rate > 0:
        return "widening", "red"
    elif gap_rate < 0:
        return "closing", "green"
    return "stable", "white"


def _dominance_color(dominance: float) -> str:
    if dominance >= 3.0:
        return "yellow"
    elif dominance >= 2.0:
        return "white"
    return "green"


class SignalsPanel(Vertical):
    """Panel displaying analytical signals and recommendation."""

    DEFAULT_CSS = """
    SignalsPanel > .signals-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    SignalsPanel > .signals-body {
        padding: 0 1;
        width: 100%;
    }
    SignalsPanel > .signals-rec {
        padding: 0 1;
        width: 100%;
        text-align: center;
        content-align: center middle;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("SIGNALS", classes="signals-title")
        yield Static("", id="sig-spacer")
        yield Static("[dim]  Loading...[/]", classes="signals-body", id="sig-late-join")
        yield Static("", classes="signals-body", id="sig-gap-trend")
        yield Static("", classes="signals-body", id="sig-dominance")
        yield Static("", id="sig-spacer-2")
        yield Static("", classes="signals-rec", id="sig-recommendation")

    def _fmt_row(self, label: str, value: str, indicator: str = "", ind_color: str = "dim") -> str:
        """Format a signal row with fixed-width columns."""
        return (
            f"  [dim]{label:<20}[/]"
            f"[bold white]{value:>12}[/]"
            f"  [{ind_color}]\u25cf {indicator:<10}[/]" if indicator else
            f"  [dim]{label:<20}[/]"
            f"[bold white]{value:>12}[/]"
        )

    def update_data(
        self,
        late_join_ev: dict[str, Any],
        gap_analysis: dict[str, Any],
        dominance: float,
        recommendation: str,
    ) -> None:
        """Update all signal lines with computed analytics."""
        # Late-Join EV
        ev_usd = late_join_ev.get("ev_usd", 0.0)
        ev_col = _ev_color(ev_usd)
        ev_ind = "positive" if ev_usd > 0 else "negative"
        self.query_one("#sig-late-join", Static).update(
            f"  [dim]{'Late-Join EV':<20}[/]"
            f"[bold white]{'${:,.2f}'.format(ev_usd):>12}[/]"
            f"  [{ev_col}]\u25cf {ev_ind:<10}[/]"
        )

        # Gap trend
        gap_rate = gap_analysis.get("gap_rate", 0.0)
        trend_label, trend_color = _gap_trend_label(gap_rate)
        self.query_one("#sig-gap-trend", Static).update(
            f"  [dim]{'Gap Trend':<20}[/]"
            f"[bold white]{trend_label:>12}[/]"
            f"  [{trend_color}]\u25cf {trend_label:<10}[/]"
        )

        # Leader dominance
        dom_col = _dominance_color(dominance)
        dom_label = "warning" if dominance >= 3.0 else "healthy"
        dom_str = f"{dominance:.1f}x" if dominance < float("inf") else "\u221ex"
        self.query_one("#sig-dominance", Static).update(
            f"  [dim]{'Leader Dominance':<20}[/]"
            f"[bold white]{dom_str:>12}[/]"
            f"  [{dom_col}]\u25cf {dom_label:<10}[/]"
        )

        # Recommendation
        self.query_one("#sig-recommendation", Static).update(
            f"  [dim]\u2192 Recommendation:[/] [bold]{recommendation}[/]"
        )
