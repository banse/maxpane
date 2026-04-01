"""Available targets summary for FrenPet Pet View."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


def _density_color(density: str) -> str:
    """Return color based on target density."""
    if density == "high":
        return "green"
    elif density == "medium":
        return "yellow"
    return "red"


class TargetLandscape(Vertical):
    """Panel showing available target counts, sweet spot, and avg ratio."""

    DEFAULT_CSS = """
    TargetLandscape {
        width: 1fr;
        height: auto;
        padding: 0 1;
    }
    TargetLandscape > .tl-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    TargetLandscape > .tl-body {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("TARGET LANDSCAPE", classes="tl-title")
        yield Static("[dim]  Loading...[/]", id="tl-content", classes="tl-body")

    def update_data(self, market_conditions: dict) -> None:
        """Update target landscape from market conditions dict.

        Parameters
        ----------
        market_conditions:
            Dict with ``available_targets``, ``sweet_spot_count``,
            ``avg_opponent_def``, ``target_density``, ``verdict`` keys.
        """
        available = market_conditions.get("available_targets", 0)
        sweet_spot = market_conditions.get("sweet_spot_count", 0)
        avg_def = market_conditions.get("avg_opponent_def", 0.0)
        density = market_conditions.get("target_density", "low")
        verdict = market_conditions.get("verdict", "conservative")

        density_col = _density_color(density)

        lines = [
            f"  [dim]Available:[/]  [bold white]{available:,}[/] pets",
            f"  [dim]Sweet spot:[/] [{density_col}]{sweet_spot}[/] (60-80% win prob)",
            f"  [dim]Avg DEF:[/]    [bold white]{avg_def:.0f}[/]",
            f"  [dim]Density:[/]    [{density_col}]{density}[/]",
            f"  [dim]Verdict:[/]    [bold white]{verdict}[/]",
        ]

        self.query_one("#tl-content", Static).update("\n".join(lines))
