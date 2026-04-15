"""Top earner and most efficient pet panels for the FrenPet Wallet view."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


def _truncate(name: str, width: int = 15) -> str:
    """Truncate a name and pad/clip to width."""
    if len(name) > width:
        return name[: width - 1] + "."
    return name.ljust(width)


def _fmt_score(score: float) -> str:
    """Format score with K/M/B suffix."""
    if score >= 1_000_000_000:
        return f"{score / 1_000_000_000:.1f}B"
    if score >= 1_000_000:
        return f"{score / 1_000_000:.1f}M"
    if score >= 1_000:
        return f"{score / 1_000:.1f}K"
    return f"{score:,.0f}"


class FPWalletBestPlays(Vertical):
    """Two sections showing top earner (by score) and most efficient (by win rate)."""

    DEFAULT_CSS = """
    FPWalletBestPlays > .fpw-bp-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    FPWalletBestPlays > .fpw-bp-body {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("BEST PLAYS", classes="fpw-bp-title")
        yield Static("", classes="fpw-bp-body", id="fpw-bp-spacer")
        yield Static(
            "[dim]  Top Earner[/]",
            classes="fpw-bp-body",
            id="fpw-bp-earner-label",
        )
        yield Static(
            "[dim]  Loading...[/]",
            classes="fpw-bp-body",
            id="fpw-bp-earner-detail",
        )
        yield Static("", classes="fpw-bp-body", id="fpw-bp-spacer-2")
        yield Static(
            "[dim]  Most Efficient[/]",
            classes="fpw-bp-body",
            id="fpw-bp-efficient-label",
        )
        yield Static(
            "[dim]  Loading...[/]",
            classes="fpw-bp-body",
            id="fpw-bp-efficient-detail",
        )

    def update_data(
        self,
        top_earner: dict | None,
        most_efficient: dict | None,
    ) -> None:
        """Show top earner by score and most efficient by win rate."""
        # -- Top Earner --
        earner_detail = self.query_one("#fpw-bp-earner-detail", Static)
        if top_earner:
            name = _truncate(top_earner.get("name", "Unknown"), 15)
            score = top_earner.get("score", 0)
            wins = top_earner.get("wins", 0)
            losses = top_earner.get("losses", 0)
            win_rate = top_earner.get("win_rate", 0.0)
            score_str = _fmt_score(score)
            earner_detail.update(
                f"  [yellow]\u2605[/] [bold white]{name}[/]\n"
                f"    [dim]Score:[/] [green]{score_str}[/]  "
                f"[dim]W/L:[/] {wins}/{losses}  "
                f"[dim]WR:[/] {win_rate:.1f}%"
            )
        else:
            earner_detail.update("[dim]  No data[/]")

        # -- Most Efficient --
        efficient_detail = self.query_one("#fpw-bp-efficient-detail", Static)
        if most_efficient:
            name = _truncate(most_efficient.get("name", "Unknown"), 15)
            win_rate = most_efficient.get("win_rate", 0.0)
            wins = most_efficient.get("wins", 0)
            losses = most_efficient.get("losses", 0)
            battles = wins + losses
            efficient_detail.update(
                f"  [yellow]\u2605[/] [bold white]{name}[/]\n"
                f"    [dim]Win Rate:[/] [green]{win_rate:.1f}%[/]  "
                f"[dim]W/L:[/] {wins}/{losses}  "
                f"[dim]Battles:[/] {battles}"
            )
        else:
            efficient_detail.update("[dim]  No qualifying pets (min 10 battles)[/]")
