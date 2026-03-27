"""Action countdown panel for FrenPet Pet View."""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

_BAR_WIDTH = 8


def _make_bar(fraction: float, width: int = _BAR_WIDTH) -> str:
    """Build a progress bar where filled = elapsed, empty = remaining."""
    fraction = max(0.0, min(1.0, fraction))
    filled = int(round(fraction * width))
    empty = width - filled
    return "\u2588" * filled + "\u2591" * empty


def _format_countdown(seconds: float) -> str:
    """Format remaining seconds as human-readable countdown."""
    if seconds <= 0:
        return "ready"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    if hours > 0:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


class NextActions(Vertical):
    """Panel showing countdown bars for stake, wheel, battle, training."""

    DEFAULT_CSS = """
    NextActions {
        width: 1fr;
        height: auto;
        padding: 0 1;
    }
    NextActions > .na-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    NextActions > .na-row {
        padding: 0 1;
        width: 100%;
        height: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("NEXT ACTIONS", classes="na-title")
        yield Static("[dim]  Loading...[/]", id="na-stake", classes="na-row")
        yield Static("", id="na-wheel", classes="na-row")
        yield Static("", id="na-battle", classes="na-row")
        yield Static("", id="na-training", classes="na-row")

    def _format_row(
        self, label: str, status_str: str, bar: str, color: str
    ) -> str:
        """Format a single action row with label, countdown, and bar."""
        return (
            f"  [dim]{label:<10}[/]"
            f"[{color}]{status_str:>8}[/]  "
            f"[{color}]{bar}[/]"
        )

    def update_data(self, pet) -> None:
        """Update action countdowns from pet model.

        Parameters
        ----------
        pet:
            A ``FrenPet`` model instance with ``staking_perks_until``,
            ``wheel_last_spin``, ``last_attack_used`` timestamps.
        """
        now = time.time()

        # Stake: time remaining until staking perks expire
        stake_remaining = pet.staking_perks_until - now
        if stake_remaining > 0:
            stake_total = 7 * 24 * 3600
            stake_elapsed = stake_total - stake_remaining
            stake_frac = max(0.0, min(1.0, stake_elapsed / stake_total))
            stake_bar = _make_bar(stake_frac)
            stake_str = _format_countdown(stake_remaining)
            # Far from ready => dim, close => yellow
            color = "yellow" if stake_remaining < 24 * 3600 else "dim"
            self.query_one("#na-stake", Static).update(
                self._format_row("Stake:", stake_str, stake_bar, color)
            )
        else:
            self.query_one("#na-stake", Static).update(
                self._format_row("Stake:", "expired", _make_bar(1.0), "red")
            )

        # Wheel: 24h cooldown from last spin
        wheel_cooldown = 24 * 3600
        wheel_remaining = (pet.wheel_last_spin + wheel_cooldown) - now
        if wheel_remaining > 0:
            wheel_frac = 1.0 - (wheel_remaining / wheel_cooldown)
            wheel_bar = _make_bar(wheel_frac)
            wheel_str = _format_countdown(wheel_remaining)
            color = "yellow" if wheel_remaining < 3600 else "dim"
            self.query_one("#na-wheel", Static).update(
                self._format_row("Wheel:", wheel_str, wheel_bar, color)
            )
        else:
            self.query_one("#na-wheel", Static).update(
                self._format_row("Wheel:", "ready", _make_bar(1.0), "green")
            )

        # Battle: 1h cooldown from last outgoing attack
        battle_cooldown = 3600
        battle_remaining = (pet.last_attack_used + battle_cooldown) - now
        if battle_remaining > 0:
            battle_frac = 1.0 - (battle_remaining / battle_cooldown)
            battle_bar = _make_bar(battle_frac)
            battle_str = _format_countdown(battle_remaining)
            color = "yellow" if battle_remaining < 600 else "dim"
            self.query_one("#na-battle", Static).update(
                self._format_row("Battle:", battle_str, battle_bar, color)
            )
        else:
            self.query_one("#na-battle", Static).update(
                self._format_row("Battle:", "ready", _make_bar(1.0), "green")
            )

        # Training: show status based on pet status field
        if pet.status == 1:
            self.query_one("#na-training", Static).update(
                self._format_row(
                    "Training:", "active", _make_bar(0.5), "yellow"
                )
            )
        else:
            self.query_one("#na-training", Static).update(
                self._format_row(
                    "Training:", "idle", _make_bar(0.0), "dim"
                )
            )
