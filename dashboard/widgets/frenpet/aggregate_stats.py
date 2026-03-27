"""Portfolio aggregate statistics for the Wallet View."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


class AggregateStats(Vertical):
    """Combined stats across all managed pets."""

    DEFAULT_CSS = """
    AggregateStats {
        width: 1fr;
        height: auto;
        padding: 0 1;
    }
    AggregateStats > .agg-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    AggregateStats > .agg-body {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("AGGREGATE", classes="agg-title")
        yield Static("[dim]  Loading...[/]", id="agg-content", classes="agg-body")

    def update_data(
        self,
        managed_pets,
        velocities: dict[int, float],
        total_score: float,
    ) -> None:
        """Show combined stats across all pets.

        Parameters
        ----------
        managed_pets:
            Sequence of FrenPet model instances.
        velocities:
            Mapping of pet_id to points-per-day velocity.
        total_score:
            Pre-computed total score across all managed pets.
        """
        if not managed_pets:
            self.query_one("#agg-content", Static).update(
                "[dim]  No wallet configured[/]"
            )
            return

        total_wins = sum(p.win_qty for p in managed_pets)
        total_losses = sum(p.loss_qty for p in managed_pets)
        total_battles = total_wins + total_losses
        win_rate = (total_wins / total_battles * 100.0) if total_battles > 0 else 0.0
        total_velocity = sum(velocities.values())

        vel_sign = "+" if total_velocity >= 0 else ""

        lines = [
            f"  [dim]Total Score:[/]     [bold white]{int(total_score):,}[/]"
            f"  [dim]({vel_sign}{int(total_velocity):,}/day)[/]",
            f"  [dim]Total Wins:[/]      [green]{total_wins:,}[/]",
            f"  [dim]Total Losses:[/]    [red]{total_losses:,}[/]",
            f"  [dim]Win Rate:[/]        [bold white]{win_rate:.1f}%[/]",
        ]

        self.query_one("#agg-content", Static).update("\n".join(lines))
