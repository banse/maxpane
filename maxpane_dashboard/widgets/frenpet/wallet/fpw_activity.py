"""Battle activity feed for the FrenPet Wallet view.

Filters battles to only those involving the wallet's pet IDs.
"""

from __future__ import annotations

import re
import time

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static

_EMOJI_RE = re.compile(
    "["
    "\U0001f300-\U0001f9ff"  # Misc symbols, emoticons, etc.
    "\U00002702-\U000027b0"  # Dingbats
    "\U0000fe00-\U0000fe0f"  # Variation selectors
    "\U0000200d"             # Zero-width joiner
    "\U000020e3"             # Combining enclosing keycap
    "]+",
    flags=re.UNICODE,
)


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

    # Points delta
    try:
        points = int(attack.get("points_delta", 0))
    except (ValueError, TypeError):
        points = 0

    # Resolve pet names
    names = pet_names or {}
    attacker_name = (
        _EMOJI_RE.sub("", names.get(int(attacker_id), f"#{attacker_id}")).strip()
        if attacker_id != "?" else "?"
    )
    defender_name = (
        _EMOJI_RE.sub("", names.get(int(defender_id), f"#{defender_id}")).strip()
        if defender_id != "?" else "?"
    )

    result_str = "[green]Won[/]" if won else "[red]Lost[/]"
    if points >= 0:
        pts_str = f"[green]+{points:,}[/]"
    else:
        pts_str = f"[red]{points:,}[/]"

    return (
        f"  [dim]{ts}[/]  "
        f"[cyan]{attacker_name}[/] \u2192 [cyan]{defender_name}[/]  "
        f"{result_str}  {pts_str}"
    )


class FPWalletActivity(Vertical):
    """Scrolling activity feed showing battles involving wallet pets."""

    DEFAULT_CSS = """
    FPWalletActivity > .fpw-feed-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    FPWalletActivity > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._seen_keys: set[str] = set()

    def compose(self) -> ComposeResult:
        yield Static("ACTIVITY", classes="fpw-feed-title")
        yield RichLog(id="fpw-activity-log", wrap=True, highlight=True, markup=True)

    def update_data(
        self,
        recent_attacks: list[dict],
        pet_ids: set[int] | None = None,
        pet_names: dict[int, str] | None = None,
    ) -> None:
        """Rewrite the log with newest attacks on top, filtered to wallet pets."""
        log = self.query_one("#fpw-activity-log", RichLog)

        if not recent_attacks:
            if not self._seen_keys:
                log.write("[dim]  No activity yet[/]")
            return

        # Filter to only attacks involving wallet pet IDs
        if pet_ids:
            filtered = [
                a for a in recent_attacks
                if (
                    int(a.get("attacker_id", -1)) in pet_ids
                    or int(a.get("defender_id", -1)) in pet_ids
                )
            ]
        else:
            filtered = recent_attacks

        if not filtered:
            if not self._seen_keys:
                log.write("[dim]  No wallet activity yet[/]")
            return

        # Track all attacks, newest first
        new_keys = set()
        for attack in filtered:
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
        for attack in filtered:
            log.write(_attack_to_markup(attack, pet_names=pet_names))

        # Scroll to top after render
        self.call_after_refresh(log.scroll_home, animate=False)
