"""Detailed pet stats box for FrenPet Pet View."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


def _make_bar(fraction: float, width: int = 10) -> str:
    """Build a progress bar using block characters.

    Returns a string like ``████████░░`` where filled portion is
    proportional to *fraction* (0.0-1.0).
    """
    fraction = max(0.0, min(1.0, fraction))
    filled = int(round(fraction * width))
    empty = width - filled
    return "\u2588" * filled + "\u2591" * empty


def _format_score(score: int | float) -> str:
    """Format score with commas."""
    return f"{int(score):,}"


class PetStats(Vertical):
    """Panel showing score, ATK, DEF, TOD with progress bar, level, wins, shrooms."""

    DEFAULT_CSS = """
    PetStats {
        width: 1fr;
        height: auto;
        padding: 0 1;
    }
    PetStats > .ps-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    PetStats > .ps-row {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("STATS", classes="ps-title")
        yield Static("[dim]  Loading...[/]", classes="ps-row", id="ps-score")
        yield Static("", classes="ps-row", id="ps-atk-def")
        yield Static("", classes="ps-row", id="ps-tod")
        yield Static("", classes="ps-row", id="ps-level-wins")
        yield Static("", classes="ps-row", id="ps-shrooms")

    def update_data(self, pet, phase: str, tod_status: dict) -> None:
        """Update stats display.

        Parameters
        ----------
        pet:
            A ``FrenPet`` model instance.
        phase:
            Growth phase string (Hatchling/Growing/Competitive/Apex).
        tod_status:
            Dict with ``hours_remaining``, ``status``, ``color`` keys.
        """
        score_str = _format_score(pet.score)

        self.query_one("#ps-score", Static).update(
            f"  [dim]Score:[/]    [bold white]{score_str}[/]"
        )

        self.query_one("#ps-atk-def", Static).update(
            f"  [dim]ATK:[/] [bold white]{pet.attack_points}[/]  "
            f"[dim]DEF:[/] [bold white]{pet.defense_points}[/]"
        )

        # TOD bar -- fraction of 72h (typical max feeding window)
        tod_hours = tod_status.get("hours_remaining", 0.0)
        tod_color = tod_status.get("color", "white")
        tod_fraction = min(tod_hours / 72.0, 1.0)
        tod_bar = _make_bar(tod_fraction)

        hours = int(tod_hours)
        minutes = int((tod_hours - hours) * 60)
        tod_time_str = f"{hours}h {minutes:02d}m"

        self.query_one("#ps-tod", Static).update(
            f"  [dim]TOD:[/]  [{tod_color}]{tod_time_str} {tod_bar}[/]"
        )

        total_battles = pet.win_qty + pet.loss_qty
        win_rate = (pet.win_qty / total_battles * 100) if total_battles > 0 else 0.0

        self.query_one("#ps-level-wins", Static).update(
            f"  [dim]Level:[/] [bold white]{pet.level}[/]  "
            f"[dim]Wins:[/] [bold white]{pet.win_qty:,}[/]  "
            f"[dim]({win_rate:.0f}%)[/]"
        )

        self.query_one("#ps-shrooms", Static).update(
            f"  [dim]Shrooms:[/] [bold white]{pet.shrooms}[/]"
        )
