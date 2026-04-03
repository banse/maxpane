"""Activity feed template -- copy and adapt for new game dashboards.

Pattern: Vertical container with a title Static and a scrolling RichLog.
De-duplicates events by a composite key.  Newest events appear on top.

Reference implementations:
  - maxpane_dashboard/widgets/frenpet/overview/fp_battle_activity.py
  - maxpane_dashboard/widgets/cattown/ct_activity_feed.py
"""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static


def _format_event_time(timestamp: float | int | str) -> str:
    """Convert a unix timestamp to HH:MM display format."""
    try:
        ts = int(timestamp)
        t = time.localtime(ts)
        return f"{t.tm_hour:02d}:{t.tm_min:02d}"
    except (ValueError, OSError, TypeError):
        return "??:??"


def _short_addr(address: str) -> str:
    """Shorten a wallet address to 0xABCD..1234 format."""
    if len(address) > 10:
        return f"{address[:6]}..{address[-4:]}"
    return address


def _event_to_markup(event: dict) -> str:
    """Convert an event dict into a Rich-markup formatted line.

    Adapt the dict keys and formatting to your game's event schema.
    """
    ts = _format_event_time(event.get("timestamp", 0))
    who = event.get("display_name", "") or _short_addr(event.get("address", ""))
    action = event.get("action", "")
    detail = event.get("detail", "")
    success = event.get("success", True)

    result_icon = "[green]\u2713[/]" if success else "[red]\u2717[/]"
    return f"  [dim]{ts}[/]  [dim]{who}[/]  [cyan]{action}[/] {detail}  {result_icon}"


class GameActivityFeed(Vertical):
    """Auto-scrolling activity feed with recent game events.

    Rename this class (and the CSS selectors) for your game, e.g.
    ``class CTActivityFeed(Vertical):``.
    """

    DEFAULT_CSS = """
    GameActivityFeed > .feed-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    GameActivityFeed > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._seen_keys: set[str] = set()

    def compose(self) -> ComposeResult:
        yield Static("ACTIVITY", classes="feed-title")
        yield RichLog(id="game-activity-log", wrap=True, highlight=True, markup=True)

    def update_data(self, events: list[dict] | None = None) -> None:
        """Rewrite the log with newest events on top.

        Events are de-duplicated by a key built from event fields.
        """
        log = self.query_one("#game-activity-log", RichLog)

        if not events:
            if not self._seen_keys:
                log.write("[dim]  No activity yet[/]")
            return

        # De-duplicate
        for event in events:
            key = f"{event.get('timestamp', '')}:{event.get('address', '')}:{event.get('action', '')}"
            self._seen_keys.add(key)

        # Clear and rewrite: newest on top
        log.clear()
        log.auto_scroll = False
        for event in events:
            log.write(_event_to_markup(event))

        # Scroll to top after render
        self.call_after_refresh(log.scroll_home, animate=False)
