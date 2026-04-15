"""Hero metric boxes for the FrenPet Performance view."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static


def _fmt_score(score: float) -> str:
    """Format score with K/M/B suffix."""
    if score >= 1_000_000_000:
        return f"{score / 1_000_000_000:.1f}B"
    if score >= 1_000_000:
        return f"{score / 1_000_000:.1f}M"
    if score >= 1_000:
        return f"{score / 1_000:.1f}K"
    return f"{score:,.0f}"


class FPPHeroBox(Static):
    """A single hero metric box with label and value."""

    DEFAULT_CSS = ""


class FPPerfHero(Horizontal):
    """Row of three hero metric boxes: Total W/L, Total Score, Avg Win Rate."""

    DEFAULT_CSS = """
    FPPerfHero > FPPHeroBox {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield FPPHeroBox(
            "[dim]TOTAL W/L[/]\n\n"
            "[dim]Loading...[/]",
            id="fpp-hero-wl",
        )
        yield FPPHeroBox(
            "[dim]TOTAL SCORE[/]\n\n"
            "[dim]Loading...[/]",
            id="fpp-hero-score",
        )
        yield FPPHeroBox(
            "[dim]AVG WIN RATE[/]\n\n"
            "[dim]Loading...[/]",
            id="fpp-hero-winrate",
        )

    def update_data(
        self,
        total_wins: int,
        total_losses: int,
        total_score: float,
        avg_win_rate: float,
        pet_count: int,
    ) -> None:
        """Refresh all three hero boxes with live values."""
        total_battles = total_wins + total_losses

        # -- Total W/L --
        wl_box = self.query_one("#fpp-hero-wl", FPPHeroBox)
        wl_box.update(
            f"[dim]TOTAL W/L[/]\n\n"
            f"[bold green]{total_wins:,}[/] / [bold red]{total_losses:,}[/]\n"
            f"[dim]{total_battles:,} total battles[/]"
        )

        # -- Total Score --
        score_box = self.query_one("#fpp-hero-score", FPPHeroBox)
        score_str = _fmt_score(total_score)
        score_box.update(
            f"[dim]TOTAL SCORE[/]\n\n"
            f"[bold white]{score_str}[/]\n"
            f"[dim]across {pet_count} pets[/]"
        )

        # -- Avg Win Rate --
        wr_box = self.query_one("#fpp-hero-winrate", FPPHeroBox)
        if avg_win_rate >= 60:
            wr_color = "green"
        elif avg_win_rate >= 40:
            wr_color = "yellow"
        else:
            wr_color = "red"
        wr_box.update(
            f"[dim]AVG WIN RATE[/]\n\n"
            f"[bold {wr_color}]{avg_win_rate:.1f}%[/]\n"
            f"[dim]across {pet_count} pets[/]"
        )
