"""Performance signals panel for the FrenPet Performance view."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


class FPPerfSignals(Vertical):
    """Panel displaying FrenPet performance analytical signals and recommendation."""

    DEFAULT_CSS = """
    FPPerfSignals > .fpp-sig-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    FPPerfSignals > .fpp-sig-body {
        padding: 0 1;
        width: 100%;
    }
    FPPerfSignals > .fpp-sig-rec {
        padding: 0 1;
        width: 100%;
        text-align: center;
        content-align: center middle;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("SIGNALS", classes="fpp-sig-title")
        yield Static("", id="fpp-sig-spacer")
        yield Static("[dim]  Loading...[/]", classes="fpp-sig-body", id="fpp-sig-winrate")
        yield Static("", classes="fpp-sig-body", id="fpp-sig-velocity")
        yield Static("", classes="fpp-sig-body", id="fpp-sig-weakest")
        yield Static("", id="fpp-sig-spacer-2")
        yield Static("", classes="fpp-sig-rec", id="fpp-sig-recommendation")

    def update_data(
        self,
        avg_win_rate: float,
        wr_status: str,
        wr_color: str,
        total_velocity: float,
        vel_status: str,
        vel_color: str,
        weakest_name: str,
        weakest_wr: float,
        weakest_status: str,
        weakest_color: str,
        recommendation: str = "",
    ) -> None:
        """Update all signal lines with computed analytics."""
        # Avg Win Rate
        wr_str = f"{avg_win_rate:.1f}%"
        self.query_one("#fpp-sig-winrate", Static).update(
            f"  [dim]{'Avg Win Rate':<20}[/]"
            f"[bold white]{wr_str:>12}[/]"
            f"  [{wr_color}]\u25cf {wr_status:<10}[/]"
        )

        # Score Velocity
        if abs(total_velocity) >= 1_000:
            vel_str = f"+{total_velocity / 1_000:.1f}K/hr"
        else:
            vel_str = f"+{total_velocity:,.0f}/hr"
        self.query_one("#fpp-sig-velocity", Static).update(
            f"  [dim]{'Score Velocity':<20}[/]"
            f"[bold white]{vel_str:>12}[/]"
            f"  [{vel_color}]\u25cf {vel_status:<10}[/]"
        )

        # Weakest Pet
        weak_str = f"{weakest_name} {weakest_wr:.0f}%"
        self.query_one("#fpp-sig-weakest", Static).update(
            f"  [dim]{'Weakest Pet':<20}[/]"
            f"[bold white]{weak_str:>12}[/]"
            f"  [{weakest_color}]\u25cf {weakest_status:<10}[/]"
        )

        # Recommendation
        self.query_one("#fpp-sig-recommendation", Static).update(
            f"  [dim]\u2192 Recommendation:[/] [bold]{recommendation}[/]"
        )
