"""Sniper targets with countdown for FrenPet Pet View.

This is the killer feature: real-time countdown to when high-value
targets become attackable, sorted by reward-risk ratio.
"""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from dashboard.analytics.frenpet_battle import (
    calculate_reward_risk_ratio,
    calculate_win_probability,
)


def _ratio_color(ratio: float) -> str:
    """Return color based on reward-risk ratio."""
    if ratio >= 5.0:
        return "green"
    elif ratio >= 2.0:
        return "yellow"
    return "red"


def _format_countdown(seconds: float) -> str:
    """Format remaining seconds as countdown string."""
    if seconds <= 0:
        return "now"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    if hours > 0:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


def _format_score_short(score: float) -> str:
    """Format score compactly: 230000 -> '230K'."""
    if abs(score) >= 1_000_000:
        return f"{score / 1_000_000:.1f}M"
    if abs(score) >= 1_000:
        return f"{score / 1_000:.0f}K"
    return f"{int(score)}"


class SniperQueue(Vertical):
    """Panel showing top sniper candidates with live countdowns."""

    DEFAULT_CSS = """
    SniperQueue {
        width: 1fr;
        height: auto;
        padding: 0 1;
    }
    SniperQueue > .sq-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    SniperQueue > DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("SNIPER QUEUE", classes="sq-title")
        yield DataTable(id="sq-table")

    def on_mount(self) -> None:
        table = self.query_one("#sq-table", DataTable)
        table.cursor_type = "none"
        table.zebra_stripes = True
        table.add_column("Pet", width=8)
        table.add_column("Score", width=8)
        table.add_column("Ratio", width=8)
        table.add_column("Bonkable", width=12)
        table.add_column("Status", width=8)

    def update_data(
        self,
        top_pets: list,
        pet_atk: int,
        pet_def: int,
        pet_score: float,
    ) -> None:
        """Show top sniper candidates with countdowns.

        Parameters
        ----------
        top_pets:
            List of ``FrenPet`` model instances from the population.
        pet_atk:
            Our pet's attack points.
        pet_def:
            Our pet's defense points.
        pet_score:
            Our pet's current score.
        """
        table = self.query_one("#sq-table", DataTable)
        table.clear()

        now = time.time()
        candidates: list[tuple[float, object]] = []

        for target in top_pets:
            # Skip targets that are hibernated or shielded
            if target.status != 0:
                continue
            if target.shield_expires > now:
                continue

            # Skip self
            if float(target.score) == pet_score and target.attack_points == pet_atk:
                continue

            win_prob = calculate_win_probability(pet_atk, target.defense_points)
            if win_prob < 0.40:
                continue

            ratio = calculate_reward_risk_ratio(
                pet_score,
                pet_atk,
                float(target.score),
                target.defense_points,
            )

            if ratio < 1.0:
                continue

            candidates.append((ratio, target))

        # Sort by ratio descending
        candidates.sort(key=lambda x: x[0], reverse=True)

        if not candidates:
            table.add_row("--", "[dim]No viable targets[/]", "--", "--", "--")
            return

        for ratio, target in candidates[:6]:
            score_str = _format_score_short(float(target.score))
            ratio_col = _ratio_color(ratio)

            # Time until bonkable (cooldown from last_attacked)
            bonkable_at = target.last_attacked + 3600
            remaining = bonkable_at - now

            if remaining <= 0:
                countdown_str = "[green]now[/]"
            else:
                countdown_str = f"[dim]{_format_countdown(remaining)}[/]"

            # Hot marker for targets bonkable within 5 minutes
            if remaining <= 300:
                status_str = "[bold red]\u25cf HOT[/]"
            else:
                status_str = "[dim]\u25cf[/]"

            table.add_row(
                f"[bold white]#{target.id}[/]",
                score_str,
                f"[{ratio_col}]{ratio:.1f}x[/]",
                countdown_str,
                status_str,
            )
