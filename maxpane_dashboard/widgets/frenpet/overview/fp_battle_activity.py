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


def _attack_to_markup(attack: dict) -> str:
    """Convert an attack dict into a Rich-markup formatted line."""
    ts = _format_time(attack.get("timestamp", 0))
    attacker = attack.get("attacker_id", "?")
    defender = attack.get("defender_id", "?")
    won = attack.get("attacker_won", False)
    points = attack.get("points_delta", 0)

    result_str = "[green]Won[/]" if won else "[red]Lost[/]"
    pts_str = f"[green]+{points:,}[/]" if points >= 0 else f"[red]{points:,}[/]"

    return (
        f"  [dim]{ts}[/]  "
        f"[cyan]#{attacker}[/] \u2192 [cyan]#{defender}[/]  "
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

    def update_data(self, recent_attacks: list[dict]) -> None:
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
            log.write(_attack_to_markup(attack))

        # Scroll to top after render
        self.call_after_refresh(log.scroll_home, animate=False)
