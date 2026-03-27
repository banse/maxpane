"""Market conditions signal panel for FrenPet General View."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


def _density_color(density: str) -> str:
    """Return color for target density level."""
    if density == "high":
        return "green"
    elif density == "medium":
        return "yellow"
    return "red"


def _verdict_color(verdict: str) -> str:
    """Return color for market verdict."""
    if verdict == "aggressive":
        return "green"
    elif verdict == "balanced":
        return "yellow"
    return "red"


def _hibernation_label(rate: float) -> tuple[str, str]:
    """Return (label, color) for hibernation rate."""
    pct = rate * 100
    if pct > 40:
        return "many targets", "green"
    elif pct > 20:
        return "moderate", "yellow"
    return "few targets", "red"


class MarketConditions(Vertical):
    """Key-value signal panel with colored dot indicators."""

    DEFAULT_CSS = """
    MarketConditions > .mc-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    MarketConditions > .mc-body {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("MARKET CONDITIONS", classes="mc-title")
        yield Static("[dim]  Loading...[/]", id="mc-content", classes="mc-body")

    def update_data(self, market_conditions: dict) -> None:
        """Update market condition signals."""
        density = market_conditions.get("target_density", "low")
        hibernation_rate = market_conditions.get("hibernation_rate", 0.0)
        shield_rate = market_conditions.get("shield_rate", 0.0)
        verdict = market_conditions.get("verdict", "conservative")

        density_col = _density_color(density)
        hib_label, hib_col = _hibernation_label(hibernation_rate)
        verdict_col = _verdict_color(verdict)

        lines = [
            (
                f"  [dim]Target density:[/]  "
                f"[bold white]{density:>8}[/]    "
                f"[{density_col}]\u25cf favorable[/]"
            ),
            (
                f"  [dim]Hibernation:[/]     "
                f"[bold white]{hibernation_rate * 100:>6.1f}%[/]    "
                f"[{hib_col}]\u25cf {hib_label}[/]"
            ),
            (
                f"  [dim]Shield rate:[/]     "
                f"[bold white]{shield_rate * 100:>6.1f}%[/]"
            ),
            (
                f"  [dim]Verdict:[/]         "
                f"[bold {verdict_col}]{verdict}[/]"
                f"          [{verdict_col}]\u25cf {verdict}[/]"
            ),
        ]

        self.query_one("#mc-content", Static).update("\n".join(lines))
