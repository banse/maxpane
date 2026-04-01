"""ATK/DEF training progress for FrenPet Pet View."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


class TrainingStatus(Vertical):
    """Panel showing training state for ATK and DEF stats."""

    DEFAULT_CSS = """
    TrainingStatus {
        width: 1fr;
        height: auto;
        padding: 0 1;
    }
    TrainingStatus > .ts-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    TrainingStatus > .ts-body {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("TRAINING", classes="ts-title")
        yield Static("[dim]  Loading...[/]", id="ts-content", classes="ts-body")

    def update_data(self, pet) -> None:
        """Show training state for both ATK and DEF.

        Parameters
        ----------
        pet:
            A ``FrenPet`` model instance.
        """
        # ATK line
        atk_val = pet.attack_points
        # DEF line
        def_val = pet.defense_points

        # Training requirements: each stat point costs (current_value) wins
        # We show how many wins are needed for next point
        total_battles = pet.win_qty + pet.loss_qty
        atk_wins_needed = atk_val  # next ATK costs current_atk wins
        def_wins_needed = def_val  # next DEF costs current_def wins

        wins_available = pet.win_qty

        lines = [
            f"  [dim]ATK:[/] [bold white]{atk_val}[/]  "
            f"[dim](next at {atk_wins_needed} wins)[/]",
            f"  [dim]DEF:[/] [bold white]{def_val}[/]  "
            f"[dim](next at {def_wins_needed} wins)[/]",
        ]

        self.query_one("#ts-content", Static).update("\n".join(lines))
