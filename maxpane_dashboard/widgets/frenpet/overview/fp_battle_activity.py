"""Battle activity feed for the FrenPet Overview view."""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static


def _format_time(timestamp) -> str:
    """Convert a timestamp to HH:MM display format."""
    try:
        ts = int(timestamp)
        t = time.localtime(ts)
        return f"{t.tm_hour:02d}:{t.tm_min:02d}"
    except (ValueError, OSError, TypeError):
        return "??:??"


def _attack_to_markup(attack: dict, pet_names: dict[int, str] | None = None) -> str:
    """Convert an attack dict into a Rich-markup formatted line."""
    ts = _format_time(attack.get("timestamp", 0))
    attacker_id = attack.get("attacker_id", "?")
    defender_id = attack.get("defender_id", "?")
    won = attack.get("attacker_won", False)

    # Points delta from `won` field (raw value in 1e12 units)
    won_raw = attack.get("won", 0)
    try:
        points = int(won_raw) / 1e12
    except (ValueError, TypeError):
        points = 0.0

    # Resolve pet names
    names = pet_names or {}
    attacker_name = names.get(int(attacker_id), f"#{attacker_id}") if attacker_id != "?" else "?"
    defender_name = names.get(int(defender_id), f"#{defender_id}") if defender_id != "?" else "?"

    result_str = "[green]Won[/]" if won else "[red]Lost[/]"
    if points >= 0:
        pts_str = f"[green]+{points:,.0f}[/]"
    else:
        pts_str = f"[red]{points:,.0f}[/]"

    return (
        f"  [dim]{ts}[/]  "
        f"[cyan]{attacker_name}[/] \u2192 [cyan]{defender_name}[/]  "
        f"{result_str}  {pts_str}"
    )


class FPBattleActivity(Vertical):
    """Scrolling activity feed showing recent FrenPet battles."""

    DEFAULT_CSS = """
    FPBattleActivity > .fpo-feed-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    FPBattleActivity > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._seen_keys: set[str] = set()

    def compose(self) -> ComposeResult:
        yield Static("ACTIVITY", classes="fpo-feed-title")
        yield RichLog(id="fpo-activity-log", wrap=True, highlight=True, markup=True)

    def update_data(
        self,
        recent_attacks: list[dict],
        pet_names: dict[int, str] | None = None,
    ) -> None:
        """Rewrite the log with newest attacks on top."""
        log = self.query_one("#fpo-activity-log", RichLog)

        if not recent_attacks:
            if not self._seen_keys:
                log.write("[dim]  No activity yet[/]")
            return

        # Track all attacks, newest first
        new_keys = set()
        for attack in recent_attacks:
            key = (
                f"{attack.get('timestamp', '')}:"
                f"{attack.get('attacker_id', '')}:"
                f"{attack.get('defender_id', '')}"
            )
            new_keys.add(key)
            self._seen_keys.add(key)

        # Clear and rewrite: newest on top
        log.clear()
        log.auto_scroll = False
        for attack in recent_attacks:
            log.write(_attack_to_markup(attack, pet_names=pet_names))

        # Scroll to top after render
        self.call_after_refresh(log.scroll_home, animate=False)
