"""Recent activity feed for the Wallet View (all managed pets)."""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static


def _format_time(ts: int | float) -> str:
    """Format a Unix timestamp as HH:MM."""
    try:
        t = time.localtime(int(ts))
        return f"{t.tm_hour:02d}:{t.tm_min:02d}"
    except (ValueError, OSError):
        return "??:??"


class WalletActivity(Vertical):
    """Scrolling log of recent battles across all managed pets."""

    DEFAULT_CSS = """
    WalletActivity {
        width: 1fr;
        height: 1fr;
        padding: 0 1;
    }
    WalletActivity > .wa-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    WalletActivity > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._seen_keys: set[str] = set()

    def compose(self) -> ComposeResult:
        yield Static("RECENT ACTIVITY (all pets)", classes="wa-title")
        yield RichLog(id="wallet-activity-log", wrap=True, highlight=True, markup=True)

    def update_data(self, attacks: list[dict]) -> None:
        """Show recent battles, filtered to managed pets only.

        Each attack dict is expected to have keys like:
        - ``timestamp``: Unix timestamp
        - ``attacker_id``: pet id of attacker
        - ``defender_id``: pet id of defender
        - ``attacker_name`` / ``defender_name``: optional display names
        - ``win``: bool indicating if attacker won
        - ``win_chance``: probability (0-100)
        - ``score_change``: points gained/lost
        """
        log = self.query_one("#wallet-activity-log", RichLog)

        if not attacks:
            if not self._seen_keys:
                log.write("[dim]  No recent activity[/]")
            return

        for attack in reversed(attacks):
            ts = attack.get("timestamp", 0)
            atk_id = attack.get("attacker_id", 0)
            def_id = attack.get("defender_id", 0)
            key = f"{ts}:{atk_id}:{def_id}"

            if key in self._seen_keys:
                continue
            self._seen_keys.add(key)

            time_str = _format_time(ts)
            chance = attack.get("win_chance", 0)
            won = attack.get("win", False)
            delta = attack.get("score_change", 0)

            result_color = "green" if won else "red"
            result_text = "Won" if won else "Lost"
            sign = "+" if delta >= 0 else ""

            line = (
                f"  [dim]{time_str}[/]  #{atk_id}  Bonked #{def_id}"
                f"  {chance:.0f}% \u2192 [{result_color}]{result_text}[/{result_color}]"
                f"  {sign}{int(delta):,}"
            )
            log.write(line)
