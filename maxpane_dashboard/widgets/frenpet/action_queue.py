"""Upcoming actions timeline for the Wallet View."""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


def _format_time(ts: float) -> str:
    """Format a Unix timestamp as HH:MM, or 'NOW' if in the past."""
    now = time.time()
    if ts <= now:
        return "NOW   "
    t = time.localtime(ts)
    return f"{t.tm_hour:02d}:{t.tm_min:02d} "


class ActionQueue(Vertical):
    """Panel showing next actions across all managed pets, sorted by urgency."""

    DEFAULT_CSS = """
    ActionQueue {
        width: 1fr;
        height: auto;
        padding: 0 1;
    }
    ActionQueue > .aq-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    ActionQueue > .aq-body {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("UPCOMING ACTIONS", classes="aq-title")
        yield Static("[dim]  Loading...[/]", id="aq-content", classes="aq-body")

    def update_data(self, managed_pets) -> None:
        """Estimate next actions for each pet and display sorted by time.

        Actions are inferred from current pet state:
        - Stake: if ``staking_perks_until`` is within 24h or already expired.
        - Wheel: if ``wheel_last_spin`` was more than 24h ago.
        - Battle: if ``last_attack_used`` cooldown (1h) has cleared.
        """
        if not managed_pets:
            self.query_one("#aq-content", Static).update(
                "[dim]  No wallet configured[/]"
            )
            return

        now = time.time()
        actions: list[tuple[float, int, str, str, bool]] = []
        # (sort_time, pet_id, action_name, label, is_urgent)

        for pet in managed_pets:
            pet_label = f"#{pet.id}"

            # -- Stake check: staking perks expiring soon --------------------
            stake_remaining = pet.staking_perks_until - now
            if stake_remaining < 0:
                # Already expired -- urgent now.
                actions.append((now, pet.id, "Stake", "Stake (expired!)", True))
            elif stake_remaining < 24 * 3600:
                # Expiring within 24h.
                urgent = stake_remaining < 6 * 3600
                actions.append(
                    (pet.staking_perks_until, pet.id, "Stake",
                     "Stake (TOD low!)" if urgent else "Stake", urgent)
                )

            # -- Wheel check: 24h cooldown from last spin --------------------
            wheel_ready = pet.wheel_last_spin + 24 * 3600
            if wheel_ready <= now:
                actions.append((now, pet.id, "Wheel spin", "Wheel spin", False))
            else:
                actions.append(
                    (wheel_ready, pet.id, "Wheel spin", "Wheel spin", False)
                )

            # -- Battle check: 1h cooldown from last attack ------------------
            battle_ready = pet.last_attack_used + 3600
            if battle_ready <= now:
                actions.append((now, pet.id, "Battle", "Battle", False))
            else:
                actions.append(
                    (battle_ready, pet.id, "Battle", "Battle", False)
                )

        # Sort: urgent first, then by time.
        actions.sort(key=lambda a: (not a[4], a[0]))

        # Limit display to 8 entries.
        display = actions[:8]

        lines: list[str] = []
        for sort_time, pid, _name, label, is_urgent in display:
            time_str = _format_time(sort_time)
            pet_str = f"#{pid}"
            if is_urgent:
                lines.append(
                    f"  [bold red]{time_str}[/]  {pet_str}  {label}"
                    f"  [bold red]\u25cf urgent[/]"
                )
            else:
                lines.append(f"  [dim]{time_str}[/]  {pet_str}  {label}")

        if not lines:
            lines.append("[dim]  No pending actions[/]")

        self.query_one("#aq-content", Static).update("\n".join(lines))
