"""Wallet signals panel for the FrenPet Wallet view."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


class FPWalletSignals(Vertical):
    """Panel displaying FrenPet wallet analytical signals and recommendation."""

    DEFAULT_CSS = """
    FPWalletSignals > .fpw-sig-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    FPWalletSignals > .fpw-sig-body {
        padding: 0 1;
        width: 100%;
    }
    FPWalletSignals > .fpw-sig-rec {
        padding: 0 1;
        width: 100%;
        text-align: center;
        content-align: center middle;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("SIGNALS", classes="fpw-sig-title")
        yield Static("", id="fpw-sig-spacer")
        yield Static("[dim]  Loading...[/]", classes="fpw-sig-body", id="fpw-sig-fp-rate")
        yield Static("", classes="fpw-sig-body", id="fpw-sig-win-rate")
        yield Static("", classes="fpw-sig-body", id="fpw-sig-pool-share")
        yield Static("", id="fpw-sig-spacer-2")
        yield Static("", classes="fpw-sig-rec", id="fpw-sig-recommendation")

    def update_data(
        self,
        fp_per_second: int,
        fp_status: str,
        fp_color: str,
        win_rate: float,
        win_status: str,
        win_color: str,
        pool_share: float,
        pool_status: str,
        pool_color: str,
        recommendation: str = "",
    ) -> None:
        """Update all signal lines with computed analytics."""
        # FP Rate
        if fp_per_second >= 1:
            fp_str = f"{fp_per_second:,.0f}/s"
        elif fp_per_second > 0:
            fp_str = f"{fp_per_second:.4f}/s"
        else:
            fp_str = "0/s"
        self.query_one("#fpw-sig-fp-rate", Static).update(
            f"  [dim]{'FP Rate':<20}[/]"
            f"[bold white]{fp_str:>12}[/]"
            f"  [{fp_color}]\u25cf {fp_status:<10}[/]"
        )

        # Win Rate
        wr_str = f"{win_rate:.1f}%"
        self.query_one("#fpw-sig-win-rate", Static).update(
            f"  [dim]{'Win Rate':<20}[/]"
            f"[bold white]{wr_str:>12}[/]"
            f"  [{win_color}]\u25cf {win_status:<10}[/]"
        )

        # Pool Share
        ps_str = f"{pool_share:.2f}%"
        self.query_one("#fpw-sig-pool-share", Static).update(
            f"  [dim]{'Pool Share':<20}[/]"
            f"[bold white]{ps_str:>12}[/]"
            f"  [{pool_color}]\u25cf {pool_status:<10}[/]"
        )

        # Recommendation
        self.query_one("#fpw-sig-recommendation", Static).update(
            f"  [dim]\u2192 Recommendation:[/] [bold]{recommendation}[/]"
        )
