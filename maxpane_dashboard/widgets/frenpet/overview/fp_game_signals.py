"""Game signals panel for the FrenPet Overview view."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


def _rate_indicator(value: float, threshold_high: float, threshold_low: float) -> tuple[str, str]:
    """Return (label, color) based on value vs thresholds."""
    if value >= threshold_high:
        return "high", "yellow"
    elif value <= threshold_low:
        return "low", "green"
    return "normal", "white"


def _dominance_color(dominance: float) -> str:
    if dominance >= 3.0:
        return "yellow"
    elif dominance >= 2.0:
        return "white"
    return "green"


class FPGameSignals(Vertical):
    """Panel displaying FrenPet game analytical signals and recommendation."""

    DEFAULT_CSS = """
    FPGameSignals > .fpo-sig-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    FPGameSignals > .fpo-sig-body {
        padding: 0 1;
        width: 100%;
    }
    FPGameSignals > .fpo-sig-rec {
        padding: 0 1;
        width: 100%;
        text-align: center;
        content-align: center middle;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("SIGNALS", classes="fpo-sig-title")
        yield Static("", id="fpo-sig-spacer")
        yield Static("[dim]  Loading...[/]", classes="fpo-sig-body", id="fpo-sig-battle-rate")
        yield Static("", classes="fpo-sig-body", id="fpo-sig-win-rate")
        yield Static("", classes="fpo-sig-body", id="fpo-sig-hibernation")
        yield Static("", classes="fpo-sig-body", id="fpo-sig-dominance")
        yield Static("", id="fpo-sig-spacer-2")
        yield Static("", classes="fpo-sig-rec", id="fpo-sig-recommendation")

    def update_data(
        self,
        battle_rate: float,
        win_rate: float,
        hibernation_rate: float,
        dominance: float,
        recommendation: str,
    ) -> None:
        """Update all signal lines with computed analytics."""
        # Battle Rate
        rate_label, rate_color = _rate_indicator(battle_rate, 100.0, 10.0)
        self.query_one("#fpo-sig-battle-rate", Static).update(
            f"  [dim]{'Battle Rate':<20}[/]"
            f"[bold white]{'~{:.0f}/hr'.format(battle_rate):>12}[/]"
            f"  [{rate_color}]\u25cf {rate_label:<10}[/]"
        )

        # Win Rate
        wr_label = "balanced" if 40 <= win_rate <= 60 else ("high" if win_rate > 60 else "low")
        wr_color = "green" if 40 <= win_rate <= 60 else "yellow"
        self.query_one("#fpo-sig-win-rate", Static).update(
            f"  [dim]{'Win Rate':<20}[/]"
            f"[bold white]{'{:.1f}%'.format(win_rate):>12}[/]"
            f"  [{wr_color}]\u25cf {wr_label:<10}[/]"
        )

        # Hibernation Rate
        hib_label, hib_color = _rate_indicator(hibernation_rate, 40.0, 10.0)
        self.query_one("#fpo-sig-hibernation", Static).update(
            f"  [dim]{'Hibernation':<20}[/]"
            f"[bold white]{'{:.1f}%'.format(hibernation_rate):>12}[/]"
            f"  [{hib_color}]\u25cf {hib_label:<10}[/]"
        )

        # Top Dominance
        dom_col = _dominance_color(dominance)
        dom_label = "warning" if dominance >= 3.0 else "healthy"
        dom_str = f"{dominance:.1f}x" if dominance < float("inf") else "\u221ex"
        self.query_one("#fpo-sig-dominance", Static).update(
            f"  [dim]{'Top Dominance':<20}[/]"
            f"[bold white]{dom_str:>12}[/]"
            f"  [{dom_col}]\u25cf {dom_label:<10}[/]"
        )

        # Recommendation
        self.query_one("#fpo-sig-recommendation", Static).update(
            f"  [dim]\u2192 Recommendation:[/] [bold]{recommendation}[/]"
        )
